# Deploy WARs from the command line

[`scripts/war_runner.py`](../scripts/war_runner.py) uploads an Android-compatible
WAR to the installed WAR Runner app, starts it, checks its HTTP response, and
prints console output. It also provides `status` and `logs` commands.

The CLI needs **Python 3.9+** with TLS support and uses only the standard
library. It does not require Flutter, the private app source, Maven, or the
Android SDK to deploy an already-built WAR. ADB is optional for USB/emulator
port forwarding. Building a WAR still requires the tools in the
[build instructions](../README.md#build).

## First deployment

1. In the installed Android app, open **Settings → Web admin**, set a password,
   and enable web admin.
2. Build an Android distribution WAR, such as
   `bash scripts/build_war.sh`. Use the output in `war_repository/`, not the
   conventional JVM WAR in `target/`.
3. Run the CLI against the admin address shown by the app:

```sh
python3 scripts/war_runner.py --url https://192.168.1.42:9443 --insecure \
  deploy war_repository/hello.war
```

The CLI prompts for the admin password without echoing it. This example uses
`--insecure` for the app's self-signed certificate on a trusted development
connection. For certificate pinning, see [TLS and authentication](#tls-and-authentication).

Successful deployment prints `Ready: http://…` to stderr and new console lines
to stdout. It leaves the WAR running and logs out its own admin session.

## Emulator and USB forwarding

Forward both the admin port and the application port:

```sh
adb forward tcp:9443 tcp:9443
adb forward tcp:8080 tcp:8080
python3 scripts/war_runner.py --insecure deploy war_repository/hello.war
```

The default admin URL is `https://localhost:9443`. Readiness uses the hostname
from that URL and the application's port returned by the admin API; it does
not use the device's advertised LAN address. For different host-side ports:

```sh
adb -s emulator-5554 forward tcp:19443 tcp:9443
adb -s emulator-5554 forward tcp:18080 tcp:8080
python3 scripts/war_runner.py --url https://localhost:19443 --insecure \
  deploy war_repository/hello.war --app-url http://localhost:18080/
```

For an HTTPS application, forward its HTTPS port and add `--ssl`:

```sh
adb forward tcp:8443 tcp:8443
python3 scripts/war_runner.py --insecure \
  deploy war_repository/vaadin-demo.war --ssl --stop-running --follow
```

Adjust device-side ports if they were changed in app Settings. Admin always
uses HTTPS; `--ssl` selects the application's protocol only.

## Repeated deployments

By default, the remote filename is `dev-<stem>-<content hash>.war`. For example,
deploying `hello.war` creates a name such as `dev-hello-a1b2c3d4e5f6.war`, avoiding
the reserved catalog filename. The app's returned metadata must match the
local file's full SHA-256 and size before the CLI starts it.

- Identical content reuses an existing upload. If it is already running with
  the requested protocol, the app keeps that deployment and its sessions.
- Changed content gets a new filename. Existing uploads are retained.
- If another WAR or a different protocol is running, deployment fails before
  upload unless `--stop-running` is supplied.
- `--stop-running` explicitly permits stopping the active WAR after the new
  upload succeeds. It also restarts an identical deployment. Stopping loses
  in-memory application state and browser sessions.
- `--name my-app.war` overrides the generated name. A catalog filename or an
  existing upload with different content is rejected. There is no automatic
  overwrite, deletion, or rollback. Delete old stopped uploads in web admin.

```sh
python3 scripts/war_runner.py --insecure \
  deploy war_repository/vaadin-demo.war --stop-running
```

The CLI snapshots the local file into temporary disk storage before login,
so a concurrent rebuild cannot change the uploaded bytes. Allow local temporary
storage roughly equal to the WAR size. It performs the same basic archive
presence checks as upload: `WEB-INF/web.xml` plus `classes.dex` or
`WEB-INF/android/runtime.jar`. This is not a full compatibility check or a WAR
converter; follow the [conversion guide](WAR_CONVERSION.md).

## Readiness and failures

After the start API returns, the CLI verifies that the requested WAR and
protocol are active and polls the application URL for an HTTP 2xx response.
`--ready-timeout 60` changes the default 30-second polling deadline.
`--app-url` can also select a specific health endpoint. Redirects are not
followed, and application requests never receive the admin password or cookie.

The app itself currently requires HTTP 200 at `/` during startup. A different
CLI readiness URL does not override this host requirement.

Global `--timeout` sets the socket timeout for API operations, including upload
and startup; the default is 300 seconds. Startup on the device and the CLI's
subsequent readiness polling are separate phases. Timed-out or interrupted
requests may already have changed device state; inspect it with `status`.
A failed readiness check leaves the application running if startup succeeded.
On deployment failure, the CLI attempts to print recent console diagnostics.

Exit codes: **0** success, **1** operation/authentication/readiness failure,
**2** invalid command-line syntax, **130** interrupted by Ctrl+C.

## Status and logs

```sh
python3 scripts/war_runner.py --insecure status
python3 scripts/war_runner.py --insecure logs
python3 scripts/war_runner.py --insecure logs --after 123 --follow
python3 scripts/war_runner.py --insecure \
  deploy war_repository/hello.war --follow > war-console.txt
```

`status` writes the admin state as JSON to stdout. `logs` prints the retained
console history, paginating through all available lines. `--after` accepts a
console sequence number. `--follow` polls every 1.5 seconds until Ctrl+C.
Stopping the CLI does not stop the WAR. Deployment prints only lines recorded
since that deployment began; `logs` can retrieve earlier retained lines.

Console output is process-wide, including Jetty and other deployments. The app
retains only its latest 1000 lines in memory. The CLI reports missing history
when detected, handles a reset sequence counter, and escapes terminal control
characters. It cannot recover logs lost when the Android process ended.

## TLS and authentication

By default, TLS uses system certificate and hostname verification. The app's
self-signed certificate normally needs one of these explicit options:

- `--cert-sha256 <fingerprint>` trusts only that certificate. Obtain its SHA-256
  fingerprint through a trusted connection, such as the browser's certificate
  viewer over your own USB/ADB forwarding. Hex with or without colons is
  accepted. Pinning replaces CA/hostname verification and checks the peer before
  any credentials or upload bytes are sent. The same pin applies to HTTPS
  application readiness; the installed app uses the same certificate for both
  listeners. Update the pin after certificate renewal or app reinstallation.
- `--insecure` skips certificate verification for both admin and HTTPS
  readiness. Use it only for a trusted development connection.

Global options go **before** `deploy`, `status`, or `logs`:

```sh
python3 scripts/war_runner.py --url https://localhost:9443 \
  --cert-sha256 "$WAR_RUNNER_CERT_SHA256" status
```

Authentication is read in this order: `--password-stdin` (one line), the
`WAR_RUNNER_PASSWORD` environment variable, or a hidden interactive prompt.
For automation, inject `WAR_RUNNER_PASSWORD` through the environment's secret
configuration, or pipe a secret provider to `--password-stdin`. No plaintext
password command-line option is provided. The session cookie is held in memory
and logout is attempted on exit. The CLI never follows API redirects or uses
proxy environment variables.

## Standalone tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use local HTTP/HTTPS servers and an ephemeral certificate generated by
OpenSSL. Install OpenSSL to run the HTTPS tests; without it those tests are
reported as skipped. They cover authentication, certificate verification and
pinning, raw uploads, conflicts, upload-before-stop ordering, HTTP/HTTPS
readiness, forwarded URLs, console pagination, and interruption cleanup.
These tests do not require the private app or alter a connected Android device.
