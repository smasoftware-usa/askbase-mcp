"""Hosted MCP server: auth, tool listing, and that every request uses only
its own caller's API key (the old hand-rolled server shared a "default"
session, so one caller could run with another's key)."""

import asyncio
import json
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
                     "get_document_chunks", "ingest_url", "ingest_website", "create_document", "create_collection",
                     "publish_documents", "list_knowledge_bases", "list_unanswered_questions", "get_unanswered_question", "suggest_answer", "list_failed_lookups",
                     "find_contacts", "get_contact", "get_contact_memory", "list_open_items", "update_open_item",
                     "find_companies", "get_company", "list_deals", "get_deal", "deal_pipeline_summary",
                     "list_deal_suggestions", "create_deal", "move_deal", "decide_deal_suggestion",
                     "ask_assistant"}
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
        api.get("/knowledge-bases").mock(return_value=Response(200, json={"knowledge_bases": [{"id": "kb1", "name": "KB"}], "total": 1}))
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


# ── Phase 3 tools ────────────────────────────────────────


def call_tool(client, name, arguments, key="ask_live_caller"):
    return tool_text(rpc(client, "tools/call", {"name": name, "arguments": arguments}, key=key))


def test_unanswered_questions(client):
    with respx.mock(base_url="https://api.test.com/v1") as api:
        route = api.get("/missing-intents").mock(return_value=Response(200, json={"total": 1, "items": [{
            "id": "m1", "cluster_label": "Shipping to Canada", "representative_query": "do you ship to canada?",
            "hit_count": 14, "member_count": 9, "status": "open", "first_seen": "2026-09-01T00:00:00Z",
            "last_seen": "2026-10-01T00:00:00Z", "has_suggestion": False}]}))
        text, err = call_tool(client, "list_unanswered_questions", {"limit": 5})
    assert not err and "Shipping to Canada" in text and "asked 14x" in text
    assert route.calls.last.request.url.params["status"] == "open"


def test_suggestion_format(client):
    with respx.mock(base_url="https://api.test.com/v1") as api:
        api.post("/missing-intents/m1/suggest").mock(return_value=Response(200, json={"suggestion": {
            "recommendation_type": "new_tool", "title": "Add order tracking",
            "description": "Customers ask where their order is.",
            "missing_methods": [{"tool_name": "get_order_status", "description": "Look up an order"}]}}))
        text, _ = call_tool(client, "suggest_answer", {"cluster_id": "m1"})
    assert "Add order tracking" in text and "New tool" in text and "get_order_status" in text


def test_contact_memory_combines_four_calls(client):
    with respx.mock(base_url="https://api.test.com/v1") as api:
        api.get("/crm/contacts/c1/cerebrum").mock(return_value=Response(200, json=[
            {"section": "preference", "content": "Vegetarian", "is_active": True, "valid_to": None},
            {"section": "fact", "content": "Old job", "is_active": False, "valid_to": "2026-01-01"}]))
        loops = api.get("/crm/contacts/c1/open-loops").mock(return_value=Response(200, json=[
            {"title": "Send tracking number", "owner": "us", "due_at": "2026-10-04T00:00:00Z"}]))
        api.get("/crm/contacts/c1/timeline-summaries").mock(return_value=Response(200, json=[
            {"period": "day", "period_key": "2026-09-30", "summary": "Asked about refunds."}]))
        api.get("/crm/contacts/c1/timeline").mock(return_value=Response(200, json=[]))
        text, err = call_tool(client, "get_contact_memory", {"contact_id": "c1"})
    assert not err and "Vegetarian" in text and "Old job" not in text  # only current facts
    assert "Send tracking number (we owe, due 2026-10-04)" in text and "Asked about refunds." in text
    assert loops.calls.last.request.url.params["status"] == "open"


def test_open_items_and_update(client):
    with respx.mock(base_url="https://api.test.com/v1") as api:
        api.get("/crm/open-loops").mock(return_value=Response(200, json={
            "total": 1, "counts": {"open": 3, "overdue": 1, "due_this_week": 1, "waiting_on_customer": 1},
            "items": [{"id": "l1", "contact_id": "c1", "title": "Call back", "owner": "us", "due_at": None,
                       "contact_name": "Ana Ruiz"}]}))
        patch = api.patch("/crm/contacts/c1/open-loops/l1").mock(
            return_value=Response(200, json={"title": "Call back", "status": "done"}))
        text, _ = call_tool(client, "list_open_items", {"due": "overdue"})
        assert "3 open, 1 overdue" in text and "Call back** for Ana Ruiz" in text
        text, err = call_tool(client, "update_open_item", {"contact_id": "c1", "item_id": "l1", "status": "done",
                                                           "note": "Called"})
        assert not err and "now done" in text
        assert json.loads(patch.calls.last.request.content) == {"status": "done", "closed_note": "Called"}
        text, err = call_tool(client, "update_open_item", {"contact_id": "c1", "item_id": "l1", "status": "deleted"})
    assert err and "status must be" in text


def test_crm_off_is_explained(client):
    with respx.mock(base_url="https://api.test.com/v1") as api:
        api.get("/crm/contacts").mock(return_value=Response(403, json={"detail": "CRM is not enabled for this project"}))
        text, err = call_tool(client, "find_contacts", {"query": "ana"})
    assert err and "CRM tools need CRM turned on" in text


def test_ask_assistant_marks_test_sessions(client):
    with respx.mock(base_url="https://api.test.com/v1") as api:
        chat = api.post("/chat").mock(return_value=Response(200, json={
            "message": "q", "response": "We ship to Canada in 5 days.", "model": "m", "latency_ms": 900,
            "sources": [{"document_title": "Shipping", "score": 0.82}]}))
        text, _ = call_tool(client, "ask_assistant", {"question": "Do you ship to Canada?"})
    body = json.loads(chat.calls.last.request.content)
    assert body["message"] == "Do you ship to Canada?" and body["context_variables"]["origin"] == "askbase-plugin/test-assistant"
    assert "user_identity" not in body and "contact_token" not in body  # anonymous: no CRM contact or memory
    assert "We ship to Canada" in text and "Shipping (score 0.82)" in text



def test_create_collection_picks_or_creates_the_knowledge_base(client):
    col = {"id": "c1", "name": "Help", "slug": "help"}
    with respx.mock(base_url="https://api.test.com/v1") as api:
        api.get("/knowledge-bases").mock(return_value=Response(200, json={"knowledge_bases": [], "total": 0}))
        kb = api.post("/knowledge-bases").mock(return_value=Response(201, json={"id": "kbnew", "name": "Knowledge base"}))
        post = api.post("/collections").mock(return_value=Response(201, json=col))
        text, err = call_tool(client, "create_collection", {"name": "Help"})
    assert not err and kb.called and json.loads(post.calls.last.request.content)["knowledge_base_id"] == "kbnew"
    assert "Created knowledge base" in text

    with respx.mock(base_url="https://api.test.com/v1") as api:
        api.get("/knowledge-bases").mock(return_value=Response(200, json={"knowledge_bases": [
            {"id": "kb1", "name": "Support"}, {"id": "kb2", "name": "Sales"}], "total": 2}))
        post = api.post("/collections").mock(return_value=Response(201, json=col))
        text, err = call_tool(client, "create_collection", {"name": "Help"})
        assert err and "several knowledge bases" in text and "Sales (`kb2`)" in text and not post.called
        text, err = call_tool(client, "create_collection", {"name": "Help", "knowledge_base_id": "kb2"})
    assert not err and json.loads(post.calls.last.request.content)["knowledge_base_id"] == "kb2"


def test_validation_errors_are_shown(client):
    with respx.mock(base_url="https://api.test.com/v1") as api:
        api.get("/knowledge-bases").mock(return_value=Response(200, json={"knowledge_bases": [{"id": "kb1", "name": "KB"}], "total": 1}))
        api.post("/collections").mock(return_value=Response(422, json={"detail": [
            {"loc": ["body", "slug"], "msg": "String should match pattern"}]}))
        text, err = call_tool(client, "create_collection", {"name": "Help", "slug": "Bad Slug"})
    assert err and "slug: String should match pattern" in text



def test_publish_documents(client):
    with respx.mock(base_url="https://api.test.com/v1") as api:
        d1 = api.post("/documents/d1/status").mock(return_value=Response(200, json={"title": "Refunds", "publication_status": "published"}))
        api.post("/documents/d2/status").mock(return_value=Response(400, json={"detail": "processing status is 'processing'"}))
        text, err = call_tool(client, "publish_documents", {"document_ids": ["d1", "d2"]})
        assert not err and "Refunds: published" in text and "`d2`: not changed" in text and "processing" in text
        assert json.loads(d1.calls.last.request.content) == {"status": "published"}
        text, err = call_tool(client, "publish_documents", {"document_ids": ["d1"], "status": "deleted"})
    assert err and "status must be" in text
