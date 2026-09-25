"""Standalone HTTPS protocol tests; no Flutter, Android SDK, or app source needed.

Run: python3 -m unittest discover -s tests -v
OpenSSL is used only to create an ephemeral test certificate.
"""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "war_runner.py"
spec = importlib.util.spec_from_file_location("war_runner", SCRIPT)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
PASSWORD = "test-password"
TOKEN = "a" * 64


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle_request(self):
        fixture = self.server.fixture
        path = urlsplit(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        fixture.requests.append((self.command, self.path, dict(self.headers), body))
        if not path.path.startswith("/api/"):
            fixture.probes += 1
            status = fixture.probe_status
            if fixture.probe_failures:
                fixture.probe_failures -= 1
                status = 503
            return self.reply(status, {"ready": status == 200})
        if self.headers.get("X-Requested-With") != "jetty-admin":
            return self.reply(403, {"error": "Missing admin header"})
        if path.path == "/api/login":
            if fixture.login_status != 200:
                return self.reply(fixture.login_status, {"error": "Login refused"}, {"Retry-After": "30"})
            if json.loads(body).get("password") != PASSWORD:
                return self.reply(401, {"error": "Wrong password"})
            fixture.authenticated = True
            return self.reply(200, {"ok": True}, {
                "Set-Cookie": "%s=%s; Path=/; Secure; HttpOnly; SameSite=Strict" % (cli.COOKIE, TOKEN)})
        if self.headers.get("Cookie") != "%s=%s" % (cli.COOKIE, TOKEN) or not fixture.authenticated:
            return self.reply(401, {"error": "Log in first"})
        if path.path == "/api/logout":
            fixture.authenticated = False
            return self.reply(200, {"ok": True})
        if path.path == "/api/state":
            if fixture.malformed_state:
                return self.reply(200, [])
            if fixture.redirect_state:
                return self.reply(302, {}, {"Location": fixture.app_url})
            return self.reply(200, fixture.state())
        if path.path == "/api/console":
            after = int(parse_qs(path.query)["after"][0])
            lines = [line for line in fixture.lines if line["seq"] > after]
            selected = lines[:fixture.page_size]
            next_seq = selected[-1]["seq"] if selected else min(after, fixture.sequence)
            return self.reply(200, {"lines": selected, "next": next_seq,
                                    "first": fixture.lines[0]["seq"] if fixture.lines else fixture.sequence + 1,
                                    "more": len(lines) > len(selected)})
        if path.path.startswith("/api/uploads/") and self.command == "PUT":
            if fixture.upload_status != 200:
                return self.reply(fixture.upload_status, {"error": "Upload refused"})
            name = path.path.rsplit("/", 1)[1]
            row = {"id": "upload-test-%d" % len(fixture.wars), "fileName": name, "name": name,
                   "uploaded": True, "sizeBytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
            if fixture.corrupt_upload:
                row["sha256"] = "0" * 64
            fixture.wars.append(row)
            return self.reply(200, fixture.state())
        if path.path == "/api/stop":
            fixture.active = None
            fixture.note("Stopped WAR")
            return self.reply(200, fixture.state())
        if path.path.startswith("/api/wars/") and path.path.endswith("/start"):
            fixture.note("Starting WAR")
            if fixture.start_status != 200:
                fixture.note("Startup diagnostic", "err")
                return self.reply(fixture.start_status, {"error": "WAR startup failed"})
            fixture.active = path.path.split("/")[3]
            fixture.use_ssl = json.loads(body)["ssl"]
            if fixture.disappear_on_start:
                fixture.active = None
            fixture.note("Hello from the WAR", "out")
            return self.reply(200, fixture.state())
        return self.reply(404, {"error": "Not found"})

    def reply(self, status, data, headers=None):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
            pass  # Readiness only needs the response status.

    do_GET = do_POST = do_PUT = handle_request


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL is required for the local HTTPS test fixture")
class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cert_dir = tempfile.TemporaryDirectory()
        cert = Path(cls.cert_dir.name) / "cert.pem"
        key = Path(cls.cert_dir.name) / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=localhost"], check=True, capture_output=True)
        cls.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cls.context.load_cert_chain(cert, key)
        der = ssl.PEM_cert_to_DER_cert(cert.read_text())
        cls.fingerprint = hashlib.sha256(der).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.cert_dir.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.war = Path(self.temp.name) / "hello.war"
        with zipfile.ZipFile(self.war, "w") as archive:
            archive.writestr("WEB-INF/web.xml", "<web-app/>")
            archive.writestr("classes.dex", b"sample-dex" * 40000)
        self.wars = []
        self.available = [{"id": "hello", "fileName": "hello.war", "uploaded": False}]
        self.active = None
        self.use_ssl = False
        self.authenticated = False
        self.login_status = self.upload_status = self.start_status = self.probe_status = 200
        self.probe_failures = self.probes = 0
        self.corrupt_upload = self.disappear_on_start = self.malformed_state = self.redirect_state = False
        self.sequence = 0
        self.lines = []
        self.page_size = 2
        self.requests = []
        self.note("Old log")
        self.app = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.admin = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.admin.socket = self.context.wrap_socket(self.admin.socket, server_side=True)
        self.url = "https://127.0.0.1:%d" % self.admin.server_port
        self.app_url = "http://127.0.0.1:%d/" % self.app.server_port
        self.threads = []
        for server in (self.app, self.admin):
            server.fixture = self
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
            thread.start()
            self.threads.append(thread)

    def tearDown(self):
        for server in (self.app, self.admin):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join()
        self.temp.cleanup()

    def state(self):
        return {"running": self.active is not None, "activeId": self.active, "ssl": self.use_ssl,
                "wars": self.wars, "available": self.available,
                "httpPort": self.app.server_port, "httpsPort": self.admin.server_port,
                "url": "http://192.0.2.1:8080/", "urls": ["http://192.0.2.1:8080/"]}

    def note(self, text, stream="note"):
        self.sequence += 1
        self.lines.append({"seq": self.sequence, "time": 1234, "text": text, "stream": stream})

    def run_cli(self, *args, tls=None, password=PASSWORD, stdin=None):
        out, err = io.StringIO(), io.StringIO()
        options = ["--url", self.url, "--timeout", "2"]
        options.extend(["--insecure"] if tls is None else tls)
        if stdin is not None:
            options.append("--password-stdin")
        environment = {} if password is None else {"WAR_RUNNER_PASSWORD": password}
        with patch.dict(os.environ, environment, clear=True), redirect_stdout(out), redirect_stderr(err):
            with patch.object(sys, "stdin", io.StringIO(stdin or "")):
                code = cli.main(options + list(args))
        return code, out.getvalue(), err.getvalue()

    def mutations(self):
        return [(method, path) for method, path, _, _ in self.requests
                if method != "GET" and path not in ("/api/login", "/api/logout")]

    def test_deploy_streams_war_checks_forwarded_host_and_prints_new_logs(self):
        code, out, err = self.run_cli("deploy", str(self.war))
        self.assertEqual(0, code, err)
        self.assertIn("Ready:", err)
        self.assertIn("Hello from the WAR", out)
        self.assertNotIn("Old log", out)
        self.assertEqual("upload-test-0", self.active)
        upload = next(r for r in self.requests if r[0] == "PUT")
        self.assertEqual(self.war.read_bytes(), upload[3])
        self.assertEqual(str(self.war.stat().st_size), upload[2]["Content-Length"])
        self.assertNotIn("Transfer-Encoding", upload[2])
        self.assertTrue(upload[1].startswith("/api/uploads/dev-hello-"))
        probe = next(r for r in self.requests if r[1] == "/")
        self.assertNotIn("Cookie", probe[2])
        self.assertNotIn("X-Requested-With", probe[2])
        self.assertFalse(self.authenticated)
        self.assertNotIn(PASSWORD, out + err)
        self.assertNotIn(TOKEN, out + err)

    def test_reuses_identical_upload_and_leaves_it_running(self):
        self.assertEqual(0, self.run_cli("deploy", str(self.war))[0])
        self.requests.clear()
        code, _, err = self.run_cli("deploy", str(self.war))
        self.assertEqual(0, code, err)
        self.assertIn("Reusing", err)
        self.assertFalse(any(m == "PUT" or p == "/api/stop" for m, p in self.mutations()))
        self.assertEqual(1, len(self.wars))

    def test_other_active_war_requires_explicit_stop_before_any_upload(self):
        self.active = "hello"
        code, _, err = self.run_cli("deploy", str(self.war))
        self.assertEqual(1, code)
        self.assertIn("--stop-running", err)
        self.assertEqual([], self.mutations())
        self.assertEqual("hello", self.active)

    def test_switch_uploads_before_stopping_and_never_deletes(self):
        self.active = "hello"
        code, _, err = self.run_cli("deploy", str(self.war), "--stop-running", "--name", "my-app.war")
        self.assertEqual(0, code, err)
        self.assertEqual([("PUT", "/api/uploads/my-app.war"), ("POST", "/api/stop"),
                          ("POST", "/api/wars/upload-test-0/start")], self.mutations())

    def test_reserved_or_changed_filename_is_not_overwritten(self):
        code, _, err = self.run_cli("deploy", str(self.war), "--name", "hello.war")
        self.assertEqual(1, code)
        self.assertIn("reserved", err)
        self.assertEqual([], self.mutations())
        self.assertEqual(0, self.run_cli("deploy", str(self.war), "--name", "custom.war")[0])
        with zipfile.ZipFile(self.war, "a") as archive:
            archive.writestr("new.txt", "new version")
        self.requests.clear()
        code, _, err = self.run_cli("deploy", str(self.war), "--name", "custom.war", "--stop-running")
        self.assertEqual(1, code)
        self.assertIn("different bytes", err)
        self.assertEqual([], self.mutations())

    def test_invalid_war_is_rejected_before_authentication(self):
        for names in ([], ["WEB-INF/web.xml"]):
            with self.subTest(names=names):
                with zipfile.ZipFile(self.war, "w") as archive:
                    for name in names:
                        archive.writestr(name, "x")
                code, _, _ = self.run_cli("deploy", str(self.war))
                self.assertEqual(1, code)
                self.assertEqual([], self.requests)

    def test_upload_failure_preserves_running_war(self):
        self.active = "hello"
        self.upload_status = 507
        code, _, err = self.run_cli("deploy", str(self.war), "--stop-running")
        self.assertEqual(1, code)
        self.assertIn("HTTP 507", err)
        self.assertEqual("hello", self.active)
        self.assertFalse(any(p == "/api/stop" for _, p in self.mutations()))

    def test_mismatched_uploaded_hash_is_never_started(self):
        self.corrupt_upload = True
        code, _, err = self.run_cli("deploy", str(self.war))
        self.assertEqual(1, code)
        self.assertIn("does not match", err)
        self.assertIsNone(self.active)

    def test_startup_failure_retrieves_diagnostics_and_logs_out(self):
        self.start_status = 409
        code, _, err = self.run_cli("deploy", str(self.war))
        self.assertEqual(1, code)
        self.assertIn("Startup diagnostic", err)
        self.assertIn("WAR startup failed", err)
        self.assertFalse(self.authenticated)

    def test_readiness_timeout_is_failure_even_when_admin_says_running(self):
        self.probe_status = 503
        code, _, err = self.run_cli("deploy", str(self.war), "--ready-timeout", "0.1")
        self.assertEqual(1, code)
        self.assertIn("Readiness timed out", err)
        self.assertIn("HTTP 503", err)
        self.assertIsNotNone(self.active)

    def test_readiness_retries_and_accepts_custom_forwarded_url(self):
        self.probe_failures = 1
        code, _, err = self.run_cli("deploy", str(self.war), "--app-url", self.app_url + "health?ready=1")
        self.assertEqual(0, code, err)
        self.assertEqual(2, self.probes)
        self.assertIn("/health?ready=1", [r[1] for r in self.requests])

    def test_readiness_rejects_stopped_or_switched_war(self):
        self.disappear_on_start = True
        code, _, err = self.run_cli("deploy", str(self.war))
        self.assertEqual(1, code)
        self.assertIn("no longer running", err)
        self.assertEqual(0, self.probes)

    def test_https_readiness_and_pinned_certificate(self):
        code, _, err = self.run_cli("deploy", str(self.war), "--ssl", tls=["--cert-sha256", self.fingerprint])
        self.assertEqual(0, code, err)
        self.assertTrue(self.use_ssl)
        self.assertIn("Ready: https://", err)
        probe = next(r for r in self.requests if r[1] == "/")
        self.assertNotIn("Cookie", probe[2])

    def test_wrong_pin_and_untrusted_certificate_send_no_password(self):
        for options in (["--cert-sha256", "0" * 64], []):
            with self.subTest(options=options):
                code, _, err = self.run_cli("status", tls=options)
                self.assertEqual(1, code)
                self.assertIn("TLS certificate", err)
                self.assertEqual([], self.requests)

    def test_bad_password_and_lockout_are_actionable(self):
        code, _, err = self.run_cli("status", password="incorrect")
        self.assertEqual(1, code)
        self.assertIn("Wrong password", err)
        self.login_status = 429
        code, _, err = self.run_cli("status")
        self.assertEqual(1, code)
        self.assertIn("Retry after 30 seconds", err)

    def test_stdin_password_and_json_status(self):
        code, out, err = self.run_cli("status", password="wrong-env-value", stdin=PASSWORD + "\n")
        self.assertEqual(0, code, err)
        self.assertEqual(False, json.loads(out)["running"])

    def test_noninteractive_missing_password_fails_without_prompt(self):
        code, _, err = self.run_cli("status", password=None)
        self.assertEqual(1, code)
        self.assertIn("WAR_RUNNER_PASSWORD", err)
        self.assertEqual([], self.requests)

    def test_redirect_does_not_forward_cookie_to_application(self):
        self.redirect_state = True
        code, _, err = self.run_cli("status")
        self.assertEqual(1, code)
        self.assertIn("Redirect refused", err)
        self.assertEqual(0, self.probes)

    def test_malformed_response_is_clean_error(self):
        self.malformed_state = True
        code, _, err = self.run_cli("status")
        self.assertEqual(1, code)
        self.assertIn("invalid JSON", err)
        self.assertNotIn("Traceback", err)

    def test_logs_paginate_reset_and_escape_terminal_controls(self):
        for n in range(6):
            self.note("line-%d" % n, "out")
        self.note("\x1b[31munsafe", "err")
        code, out, err = self.run_cli("logs", "--after", "999")
        self.assertEqual(0, code, err)
        self.assertIn("console restarted", out)
        for n in range(6):
            self.assertEqual(1, out.count("line-%d" % n))
        self.assertNotIn("\x1b", out)
        self.assertIn("\\x1b[31munsafe", out)

    def test_logs_report_ring_buffer_gap(self):
        for n in range(6):
            self.note("line-%d" % n)
        self.lines = self.lines[4:]
        code, out, err = self.run_cli("logs", "--after", "1")
        self.assertEqual(0, code, err)
        self.assertIn("no longer available", out)

    def test_follow_interruption_logs_out_without_stopping_war(self):
        self.active = "hello"
        with patch.object(cli.time, "sleep", side_effect=KeyboardInterrupt):
            code, out, err = self.run_cli("logs", "--follow")
        self.assertEqual(130, code)
        self.assertIn("Old log", out)
        self.assertIn("Interrupted", err)
        self.assertFalse(self.authenticated)
        self.assertEqual("hello", self.active)
        self.assertEqual([], self.mutations())


class LocalTests(unittest.TestCase):
    def test_command_line_help_runs_from_outside_checkout(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "deploy", "--help"],
                                cwd=tempfile.gettempdir(), text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--app-url", result.stdout)

    def test_rejects_bad_urls_timeouts_and_cursor_values(self):
        for value in ("http://localhost:9443", "https://user:secret@host", "https://host/admin",
                      "https://host:99999", "https://host/?query", "https://host/#fragment"):
            with self.subTest(url=value), self.assertRaises(cli.CliError):
                cli.endpoint(value, admin=True)
        for value in ("0", "-1", "nan", "inf"):
            with self.subTest(timeout=value), self.assertRaises(cli.argparse.ArgumentTypeError):
                cli.positive_seconds(value)
        with self.assertRaises(cli.argparse.ArgumentTypeError):
            cli.cursor("-1")

    def test_artifact_snapshot_is_stable_if_source_changes(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryFile() as snapshot:
            path = Path(directory) / "app.war"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("WEB-INF/web.xml", "<web-app/>")
                archive.writestr("WEB-INF/android/runtime.jar", b"runtime")
            original = path.read_bytes()
            size, checksum = cli.snapshot_war(path, snapshot)
            path.write_bytes(b"changed during deployment")
            self.assertEqual(original, snapshot.read())
            self.assertEqual(len(original), size)
            self.assertEqual(hashlib.sha256(original).hexdigest(), checksum)


if __name__ == "__main__":
    unittest.main()
