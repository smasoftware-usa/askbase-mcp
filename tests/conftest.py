"""Shared fixtures. The MCP session manager runs once per app, so every
module shares one TestClient for the whole session."""

import os

import pytest
from starlette.testclient import TestClient

os.environ["ASK_API_BASE_URL"] = "https://api.test.com"


@pytest.fixture(scope="session")
def client():
    os.environ.pop("ASK_API_KEY", None)
    from askbase_mcp.http_server import app

    with TestClient(app) as c:
        yield c
