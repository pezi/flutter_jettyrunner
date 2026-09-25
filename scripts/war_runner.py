#!/usr/bin/env python3
"""Deploy Android-compatible WARs through WAR Runner's HTTPS admin API.

Python 3.9+, standard library only. See docs/DEPLOYMENT_CLI.md.
"""

import argparse
import getpass
import hashlib
import hmac
import http.client
from http.cookies import SimpleCookie
import json
import math
import os
from pathlib import Path
import re
import ssl
import sys
import tempfile
import time
from urllib.parse import quote, urlsplit
import zipfile


COOKIE = "__Host-jetty-admin"
MAX_WAR_BYTES = 1024 * 1024 * 1024
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_CURSOR = 9223372036854775807
FILE_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,119}\.war\Z")


class CliError(Exception):
    """An actionable error, displayed without a traceback."""


def safe_text(value):
    """Do not interpret terminal control sequences from remote logs/errors."""
    return "".join(c if c.isprintable() or c == "\t" else "\\x%02x" % ord(c)
                   for c in str(value))


def endpoint(value, admin=False):
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme in (("https",) if admin else ("http", "https"))
                 and parsed.hostname and not parsed.username and not parsed.password
                 and not parsed.fragment and (parsed.port is None or parsed.port > 0)
                 and not any(c.isspace() or ord(c) < 32 for c in value))
        if admin:
            valid = valid and parsed.path in ("", "/") and not parsed.query
        if not valid:
            raise ValueError()
        return parsed
    except ValueError:
        kind = "an HTTPS origin, e.g. https://localhost:9443" if admin else "an HTTP(S) URL"
        raise CliError("Expected %s without credentials or a fragment." % kind) from None


class Transport:
    def __init__(self, insecure=False, fingerprint=None):
        self.fingerprint = fingerprint
        self.context = ssl.create_default_context()
        if insecure or fingerprint:
            self.context.check_hostname = False
            self.context.verify_mode = ssl.CERT_NONE

    def request(self, url, method, path, headers=None, body=None, timeout=30, read_body=True):
        connection = (http.client.HTTPSConnection(url.hostname, url.port, timeout=timeout,
                                                  context=self.context)
                      if url.scheme == "https" else
                      http.client.HTTPConnection(url.hostname, url.port, timeout=timeout))
        try:
            connection.connect()
            # Authenticate the peer before sending passwords, cookies or WAR bytes.
            if url.scheme == "https" and self.fingerprint:
                actual = hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest()
                if not hmac.compare_digest(actual, self.fingerprint):
                    raise CliError("TLS certificate fingerprint does not match; no request was sent.")
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            content = response.read(MAX_RESPONSE_BYTES + 1) if read_body else b""
            if len(content) > MAX_RESPONSE_BYTES:
                raise CliError("Server response is too large.")
            # http.client never follows redirects, including login/upload redirects.
            return response.status, dict(response.getheaders()), content
        except ssl.SSLCertVerificationError:
            raise CliError("TLS certificate verification failed. For the app's self-signed "
                           "certificate, use --cert-sha256 with a trusted fingerprint, or "
                           "--insecure for a trusted development connection.") from None
        except (OSError, http.client.HTTPException) as error:
            raise CliError("Connection to %s:%s failed: %s. Check the address and port forwarding."
                           % (url.hostname, url.port or (443 if url.scheme == "https" else 80), error)) from None
        finally:
            connection.close()


class AdminClient:
    def __init__(self, url, transport, timeout):
        self.url = endpoint(url, admin=True)
        self.transport = transport
        self.timeout = timeout
        self.token = None

    def request(self, method, path, data=None, upload=None, size=None, timeout=None):
        headers = {"X-Requested-With": "jetty-admin", "Accept": "application/json"}
        if self.token:
            headers["Cookie"] = "%s=%s" % (COOKIE, self.token)
        if upload is not None:
            body = upload
            headers.update({"Content-Type": "application/octet-stream", "Content-Length": str(size)})
        else:
            body = None if data is None else json.dumps(data).encode("utf-8")
            if body is not None:
                headers["Content-Type"] = "application/json"
        status, response_headers, content = self.transport.request(
            self.url, method, path, headers, body,
            self.timeout if timeout is None else timeout)
        try:
            result = json.loads(content)
        except (ValueError, UnicodeError):
            result = None
        if not 200 <= status < 300:
            detail = result.get("error") if isinstance(result, dict) else None
            if status == 401:
                detail = "Wrong password or expired session; authenticate again."
            elif status == 429:
                retry = next((v for k, v in response_headers.items() if k.lower() == "retry-after"), "unknown")
                detail = "Login is locked. Retry after %s seconds." % retry
            elif 300 <= status < 400:
                detail = "Redirect refused; use the device's direct admin URL."
            raise CliError("%s %s: HTTP %s%s" % (method, path, status, ": " + str(detail) if detail else ""))
        if not isinstance(result, dict):
            raise CliError("%s returned invalid JSON; check the admin URL and app version." % path)
        if path == "/api/login":
            cookies = SimpleCookie()
            for key, value in response_headers.items():
                if key.lower() == "set-cookie":
                    cookies.load(value)
            token = cookies[COOKIE].value if COOKIE in cookies else ""
            if not re.fullmatch(r"[0-9a-f]{64}", token):
                raise CliError("Login did not return a WAR Runner session cookie.")
            self.token = token
        return result

    def logout(self):
        if self.token:
            try:
                self.request("POST", "/api/logout", timeout=min(self.timeout, 5))
            except CliError:
                pass  # Cleanup must not hide the deployment result or an interruption.
            finally:
                self.token = None


def snapshot_war(path, destination):
    """Keep a stable disk snapshot; large WARs are never held entirely in RAM."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            if size > MAX_WAR_BYTES:
                raise CliError("The WAR is larger than the app's 1 GiB upload limit.")
            destination.write(chunk)
            digest.update(chunk)
    destination.seek(0)
    try:
        with zipfile.ZipFile(destination) as archive:
            names = set(archive.namelist())
            if "WEB-INF/web.xml" not in names:
                raise CliError("The WAR has no WEB-INF/web.xml.")
            if not names.intersection({"classes.dex", "WEB-INF/android/runtime.jar"}):
                raise CliError("The WAR has no Android bytecode. Use the converted file in war_repository/.")
    except zipfile.BadZipFile:
        raise CliError("The file is not a valid WAR archive.") from None
    destination.seek(0)
    return size, digest.hexdigest()


def war_rows(state, key):
    rows = state.get(key)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise CliError("Invalid admin state: missing %s list." % key)
    return rows


def log_page(client, after, timeout=None):
    page = client.request("GET", "/api/console?after=%d" % after, timeout=timeout)
    if (not isinstance(page.get("lines"), list)
            or type(page.get("next")) is not int or not 0 <= page["next"] <= MAX_CURSOR
            or type(page.get("first")) is not int or page["first"] < 1
            or type(page.get("more")) is not bool):
        raise CliError("Invalid console response.")
    return page


def print_logs(client, after=0, output=None, timeout=None):
    output = output or sys.stdout
    for _ in range(100):
        page = log_page(client, after, timeout)
        if page["next"] < after:
            print("[console restarted; reading retained history]", file=output)
            after = 0
            continue
        if after and page["first"] > after + 1:
            print("[older console lines are no longer available]", file=output)
        for line in page["lines"]:
            if not isinstance(line, dict):
                raise CliError("Invalid console line.")
            print("[%s %s] %s" % (safe_text(line.get("seq", "?")),
                                    safe_text(line.get("stream", "?")),
                                    safe_text(line.get("text", ""))), file=output, flush=True)
        if not page["more"]:
            return page["next"]
        if page["next"] <= after:
            raise CliError("Console pagination did not advance.")
        after = page["next"]
    print("[console is busy; use logs --follow to continue]", file=output)
    return after


def follow_logs(client, after):
    while True:
        after = print_logs(client, after)
        time.sleep(1.5)


def readiness(client, war_id, use_ssl, app_url, wait):
    deadline = time.monotonic() + wait
    last_error = "No ready response received."
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        state = client.request("GET", "/api/state", timeout=min(client.timeout, remaining))
        if not state.get("running") or state.get("activeId") != war_id or state.get("ssl") != use_ssl:
            raise CliError("The requested WAR is no longer running with the requested protocol.")
        if app_url is None:
            port = state.get("httpsPort" if use_ssl else "httpPort")
            if type(port) is not int or not 1 <= port <= 65535:
                raise CliError("Invalid application port in admin state.")
            host = client.url.hostname
            host = "[%s]" % host if ":" in host else host
            url = "%s://%s:%d/" % ("https" if use_ssl else "http", host, port)
        else:
            url = app_url
        parsed = endpoint(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            # No admin cookie or password is ever sent to an application endpoint.
            status, _, _ = client.transport.request(
                parsed, "GET", (parsed.path or "/") + ("?" + parsed.query if parsed.query else ""),
                timeout=min(5, client.timeout, remaining), read_body=False)
            if 200 <= status < 300:
                return url
            last_error = "Readiness endpoint returned HTTP %d." % status
        except CliError as error:
            last_error = str(error)
        time.sleep(min(0.5, max(0, deadline - time.monotonic())))
    raise CliError("Readiness timed out: %s Check the app port forwarding or set --app-url." % last_error)


def deploy(client, args, artifact, size, checksum):
    stem = re.sub(r"[^a-z0-9_-]+", "-", args.war.stem.lower()).strip("-_")[:60] or "app"
    name = args.name or "dev-%s-%s.war" % (stem, checksum[:12])
    state = client.request("GET", "/api/state")
    installed = war_rows(state, "wars")
    all_rows = installed + war_rows(state, "available")
    matches = [row for row in all_rows if str(row.get("fileName", "")).lower() == name.lower()]
    existing = matches[0] if matches else None
    if existing is not None and (not existing.get("uploaded")
                                or existing.get("sha256") != checksum or existing.get("sizeBytes") != size):
        raise CliError("%s is reserved or contains different bytes. Choose another --name; "
                       "existing WARs are never deleted automatically." % name)
    same_running = (existing is not None and state.get("running")
                    and state.get("activeId") == existing.get("id") and state.get("ssl") == args.ssl)
    if state.get("running") and not same_running and not args.stop_running:
        raise CliError("Another WAR or protocol is running. Use --stop-running to switch it explicitly.")
    after = log_page(client, MAX_CURSOR)["next"]
    try:
        if existing is None:
            print("Uploading %s (%d bytes)…" % (name, size), file=sys.stderr)
            state = client.request("PUT", "/api/uploads/" + quote(name, safe=""), upload=artifact, size=size)
            existing = next((row for row in war_rows(state, "wars") if row.get("fileName") == name), None)
            if (existing is None or not existing.get("uploaded") or existing.get("sha256") != checksum
                    or existing.get("sizeBytes") != size):
                raise CliError("Uploaded WAR metadata does not match the local artifact; it was not started.")
        else:
            print("Reusing %s." % name, file=sys.stderr)
        war_id = existing.get("id")
        if not isinstance(war_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", war_id):
            raise CliError("Invalid uploaded WAR ID.")
        # Upload validation succeeds before any requested stop. The server also
        # checks active state when starting; competing clients may cause a 409.
        current = client.request("GET", "/api/state")
        if current.get("running") and args.stop_running:
            client.request("POST", "/api/stop")
        elif current.get("running") and (current.get("activeId") != war_id or current.get("ssl") != args.ssl):
            raise CliError("Another WAR started during deployment. Use --stop-running to switch it explicitly.")
        client.request("POST", "/api/wars/%s/start" % war_id, {"ssl": args.ssl})
        url = readiness(client, war_id, args.ssl, args.app_url, args.ready_timeout)
        print("Ready: %s (%s)" % (safe_text(url), war_id), file=sys.stderr)
        after = print_logs(client, after)
    except CliError:
        print("Deployment failed; recent console output:", file=sys.stderr)
        try:
            print_logs(client, after, output=sys.stderr, timeout=min(client.timeout, 5))
        except CliError as error:
            print("Could not retrieve logs: %s" % safe_text(error), file=sys.stderr)
        raise
    if args.follow:
        follow_logs(client, after)


def positive_seconds(value):
    try:
        number = float(value)
        if math.isfinite(number) and number > 0:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("must be a finite number greater than zero")


def cursor(value):
    try:
        number = int(value)
        if 0 <= number <= MAX_CURSOR:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("must be an integer between 0 and %d" % MAX_CURSOR)


def fingerprint(value):
    value = value.replace(":", "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise argparse.ArgumentTypeError("must be a SHA-256 certificate fingerprint (64 hex digits)")
    return value


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--url", default="https://localhost:9443", help="admin HTTPS origin (default: %(default)s)")
    tls = root.add_mutually_exclusive_group()
    tls.add_argument("--insecure", action="store_true", help="skip TLS verification for trusted development connections")
    tls.add_argument("--cert-sha256", type=fingerprint, help="trust only this certificate, including for HTTPS readiness")
    root.add_argument("--password-stdin", action="store_true", help="read one password line from stdin")
    root.add_argument("--timeout", type=positive_seconds, default=300, help="API socket timeout in seconds (default: %(default)s)")
    commands = root.add_subparsers(dest="command", required=True)
    command = commands.add_parser("deploy", help="upload a converted WAR, start it, check readiness, and print new logs")
    command.add_argument("war", type=Path, help="Android distribution WAR, normally from war_repository/")
    command.add_argument("--name", help="remote filename; default: dev-<stem>-<content hash>.war")
    command.add_argument("--ssl", action="store_true", help="serve the WAR over HTTPS (admin always uses HTTPS)")
    command.add_argument("--stop-running", action="store_true", help="stop any running WAR before start; restarts an identical deployment")
    command.add_argument("--app-url", help="readiness URL override, e.g. http://localhost:18080/")
    command.add_argument("--ready-timeout", type=positive_seconds, default=30, help="readiness polling deadline in seconds (default: %(default)s)")
    command.add_argument("--follow", action="store_true", help="continue streaming console output until Ctrl+C")
    commands.add_parser("status", help="print admin state as JSON")
    command = commands.add_parser("logs", help="print retained console history")
    command.add_argument("--after", type=cursor, default=0, help="read after this sequence number (default: all retained history)")
    command.add_argument("--follow", action="store_true", help="poll for new output until Ctrl+C")
    return root


def password(args):
    if args.password_stdin:
        value = sys.stdin.readline().rstrip("\r\n")
    elif "WAR_RUNNER_PASSWORD" in os.environ:
        value = os.environ["WAR_RUNNER_PASSWORD"]
    elif sys.stdin.isatty():
        value = getpass.getpass("Web admin password: ")
    else:
        raise CliError("Set WAR_RUNNER_PASSWORD or use --password-stdin for non-interactive use.")
    if not 6 <= len(value) <= 256:
        raise CliError("The web admin password must contain 6–256 characters.")
    return value


def main(argv=None):
    args = parser().parse_args(argv)
    client = None
    artifact = None
    try:
        client = AdminClient(args.url, Transport(args.insecure, args.cert_sha256), args.timeout)
        if args.command == "deploy":
            if args.name is not None and not FILE_NAME.fullmatch(args.name):
                raise CliError("--name must use letters, digits, '.', '_' or '-' and end in .war (up to 124 characters).")
            if args.app_url:
                endpoint(args.app_url)
            artifact = tempfile.TemporaryFile()
            size, checksum = snapshot_war(args.war, artifact)
        client.request("POST", "/api/login", {"password": password(args)})
        if args.command == "deploy":
            deploy(client, args, artifact, size, checksum)
        elif args.command == "status":
            print(json.dumps(client.request("GET", "/api/state"), indent=2))
        else:
            after = print_logs(client, args.after)
            if args.follow:
                follow_logs(client, after)
        return 0
    except (CliError, OSError, EOFError) as error:
        print("Error: %s" % safe_text(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    finally:
        if client is not None:
            client.logout()
        if artifact is not None:
            artifact.close()


if __name__ == "__main__":
    sys.exit(main())
