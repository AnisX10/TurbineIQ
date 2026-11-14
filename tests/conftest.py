"""Test-wide settings. Imported before any test module builds the API app."""

import os

# Starlette's TestClient sends ``Host: testserver``; the API only trusts local hosts otherwise.
os.environ.setdefault("TURBINEIQ_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
