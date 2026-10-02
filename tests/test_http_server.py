"""Hosted MCP server: auth, tool listing, and that every request uses only
its own caller's API key (the old hand-rolled server shared a "default"
session, so one caller could run with another's key)."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
import respx
from httpx import Response
from starlette.testclient import TestClient

os.environ["ASK_API_BASE_URL"] = "https://api.test.com"
os.environ.pop("ASK_API_KEY", None)

from askbase_mcp.http_server import app  # noqa: E402

H = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def rpc(client, method, params=None, key=None, headers=None):
    h = dict(H)
    if key:
        h["X-API-Key"] = key
    h.update(headers or {})
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}, headers=h)


def tool_text(response):
    body = response.json()
    assert "result" in body, body
    return body["result"]["content"][0]["text"], body["result"].get("isError", False)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/health").json()["status"] == "healthy"


def test_mcp_without_key_is_401(client):
    r = rpc(client, "tools/list")
    assert r.status_code == 401 and "X-API-Key" in r.json()["error"]


def test_bearer_token_is_accepted(client):
    r = rpc(client, "tools/list", headers={"Authorization": "Bearer ask_live_bearer"})
    assert r.status_code == 200


def test_tools_list_has_no_ctx_parameter(client):
    tools = rpc(client, "tools/list", key="ask_live_a").json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert names == {"search", "list_collections", "get_collection_stats", "list_documents", "get_document",
                     "get_document_chunks", "ingest_url", "ingest_website", "create_document", "create_collection"}
    for t in tools:
        assert "ctx" not in t["inputSchema"].get("properties", {}), t["name"]


def test_search_uses_the_callers_key_and_formats(client):
    with respx.mock(base_url="https://api.test.com/v1") as api:
        route = api.post("/query").mock(return_value=Response(200, json={
            "query": "refund policy", "total_results": 1, "latency_ms": 12, "search_type": "hybrid",
            "results": [{"chunk_id": "c1", "document_id": "d1", "collection_id": "k1", "content": "30 days.",
                         "score": 0.91, "document_title": "Refunds", "source_uri": None, "heading": "Policy",
                         "chunk_index": 0}]}))
        text, is_error = tool_text(rpc(client, "tools/call", {"name": "search", "arguments": {"query": "refund policy"}},
                                       key="ask_live_caller"))
    assert not is_error
    assert route.calls.last.request.headers["X-API-Key"] == "ask_live_caller"
    assert "Refunds › Policy" in text and "30 days." in text


def test_api_errors_are_explained(client):
    with respx.mock(base_url="https://api.test.com/v1") as api:
        api.post("/collections").mock(return_value=Response(403, json={"detail": "Missing required scopes: write"}))
        text, is_error = tool_text(rpc(client, "tools/call", {"name": "create_collection", "arguments": {"name": "Docs"}},
                                       key="ask_live_readonly"))
    assert is_error and "'write' scope" in text and "Missing required scopes: write" in text


def test_concurrent_callers_never_share_keys(client):
    """Regression for the shared-session bug: many callers at once, each
    request reaches the API with exactly its own key."""
    seen = []

    def handler(request):
        seen.append((request.headers["X-API-Key"], request.url.params.get("limit")))
        return Response(200, json=[])

    keys = [f"ask_live_tenant{i}" for i in range(12)]
    with respx.mock(base_url="https://api.test.com/v1") as api:
        api.get("/collections").mock(side_effect=handler)

        def one(i):
            return rpc(client, "tools/call", {"name": "list_collections", "arguments": {"limit": i + 1}}, key=keys[i])

        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(one, range(len(keys))))
    assert all(r.status_code == 200 for r in responses)
    # limit i+1 was sent by keys[i]: each request carried its own caller's key.
    assert sorted(seen) == sorted((keys[i], str(i + 1)) for i in range(len(keys)))
