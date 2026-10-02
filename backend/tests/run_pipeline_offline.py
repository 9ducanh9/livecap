"""Run pytest with application sockets/DNS forbidden; no real AWS credentials.

Windows CPython's internal socketpair bootstrap is allowed, never an application
connection. Run from backend: python -B tests/run_pipeline_offline.py tests/...
"""
from __future__ import annotations

import os
import socket
import sys
import traceback
from pathlib import Path
from unittest.mock import patch


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.update(AWS_EC2_METADATA_DISABLED="true", AWS_ACCESS_KEY_ID="offline-validation",
                      AWS_SECRET_ACCESS_KEY="offline-validation")
    for name in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_SESSION_TOKEN", "AWS_WEB_IDENTITY_TOKEN_FILE",
                 "AWS_ROLE_ARN", "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", "AWS_CONTAINER_CREDENTIALS_FULL_URI"):
        os.environ.pop(name, None)
    denied = []
    socket_source = Path(socket.__file__).resolve()

    def guarded(original):
        def connect(sock, address):
            caller = sys._getframe(1)
            if (caller.f_code.co_name == "_fallback_socketpair" and
                    Path(caller.f_code.co_filename).resolve() == socket_source and
                    isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}):
                return original(sock, address)
            denied.append("connect")
            raise AssertionError("Application network forbidden in backend validation")
        return connect

    def deny(*args, **kwargs):
        denied.append([(Path(frame.filename).name, frame.name, frame.lineno)
                       for frame in traceback.extract_stack(limit=32)[:-1]])
        raise AssertionError("Application network forbidden in backend validation")

    originals = {"connect": socket.socket.connect, "connect_ex": socket.socket.connect_ex,
                 "create_connection": socket.create_connection, "getaddrinfo": socket.getaddrinfo,
                 "sendto": socket.socket.sendto}
    try:
        socket.socket.connect = guarded(originals["connect"])
        socket.socket.connect_ex = guarded(originals["connect_ex"])
        socket.socket.sendto = deny
        socket.create_connection = deny
        socket.getaddrinfo = deny
        import pytest

        # ASGI lifespan tests must not initialize the existing Watchtower AWS
        # handler. Unit tests of setup_logging still mock its SDK separately.
        class OfflineStartup:
            application = None
            original_setup = None
            audit_sdk_patch = None

            def pytest_collection_finish(self, session):
                application = sys.modules.get("app.main")
                if application is None:
                    return
                self.application = application
                self.original_setup = application.setup_logging
                application.setup_logging = lambda **kwargs: None
                # A legacy admin route test omits this DynamoDB read fixture.
                # Mock only this module's SDK reference, not global boto3 or
                # the audit function; test-specific mocks still override it.
                from app.services import admin_audit
                self.audit_sdk_patch = patch.object(admin_audit, "boto3")
                sdk = self.audit_sdk_patch.start()
                sdk.resource.return_value.Table.return_value.query.return_value = {"Items": []}

        startup = OfflineStartup()
        try:
            result = pytest.main(sys.argv[1:] or ["tests/test_pipeline_instrumentation.py", "-q"], plugins=[startup])
        finally:
            if startup.application is not None:
                startup.application.setup_logging = startup.original_setup
            if startup.audit_sdk_patch is not None:
                startup.audit_sdk_patch.stop()
        print(f"Application network attempts blocked: {len(denied)}")
        for entry in denied:
            print("Blocked call sites:", entry)
        return result or int(bool(denied))
    finally:
        socket.socket.connect = originals["connect"]
        socket.socket.connect_ex = originals["connect_ex"]
        socket.socket.sendto = originals["sendto"]
        socket.create_connection = originals["create_connection"]
        socket.getaddrinfo = originals["getaddrinfo"]


if __name__ == "__main__":
    raise SystemExit(main())
