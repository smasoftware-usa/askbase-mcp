"""C4: company, deal and deal-suggestion tools against a mocked AskBase API."""

import json
import os

import pytest
import respx
from httpx import Response

os.environ["ASK_API_BASE_URL"] = "https://api.test.com"
os.environ.pop("ASK_API_KEY", None)

from .test_http_server import call_tool  # noqa: E402

PIPELINES = [{"id": "p1", "name": "Sales", "is_default": True, "stages": [
    {"id": "s1", "name": "New", "probability": 10, "kind": "open"},
    {"id": "s2", "name": "Proposal", "probability": 50, "kind": "open"},
    {"id": "s3", "name": "Won", "probability": 100, "kind": "won"},
    {"id": "s4", "name": "Lost", "probability": 0, "kind": "lost"}]}]

DEAL = {"id": "d1", "name": "20 seats", "amount": "4800.00", "currency": "USD", "stage_name": "New",
        "probability": 10, "status": "open", "pipeline_id": "p1", "expected_close_date": "2026-11-30",
        "company_id": "co1", "company_name": "Acme", "primary_contact_id": "c1", "primary_contact_name": "Ana Ruiz",
        "contacts": [{"contact_id": "c1", "role": "decision_maker", "name": "Ana Ruiz", "email": "ana@acme.com"}],
        "at_risk_since": None, "source": "suggestion", "created_at": "2026-10-01T00:00:00Z"}

SUGGESTION = {"id": "g1", "kind": "new_deal", "status": "pending", "title": "25 seats", "amount": "6000.00",
              "currency": "USD", "evidence": "can you quote 25 seats?", "contact_name": "Carla",
              "deal_id": None, "deal_name": None, "suggested_stage_name": None, "created_at": "2026-10-03T00:00:00Z"}




def test_tools_are_listed(client):
    from .test_http_server import rpc

    names = {t["name"] for t in rpc(client, "tools/list", key="k").json()["result"]["tools"]}
    assert {"find_companies", "get_company", "list_deals", "get_deal", "deal_pipeline_summary",
            "list_deal_suggestions", "create_deal", "move_deal", "decide_deal_suggestion"} <= names


def test_company_with_deals_and_suggestions(client):
    with respx.mock(base_url="https://api.test.com/v1") as api:
        api.get("/crm/companies/co1").mock(return_value=Response(200, json={
            "id": "co1", "name": "Acme", "domain": "acme.com", "industry": "Software & SaaS", "contact_count": 1,
            "tags": [], "contacts": [{"id": "c1", "first_name": "Ana", "last_name": "Ruiz", "job_title": "CTO",
                                      "last_seen_at": "2026-10-02T00:00:00Z"}]}))
        deals = api.get("/crm/deals").mock(return_value=Response(200, json={"deals": [DEAL], "total": 1}))
        api.get("/crm/deal-suggestions").mock(return_value=Response(200, json=[SUGGESTION]))
        text, err = call_tool(client, "get_company", {"company_id": "co1"})
    assert not err and "# Acme" in text and "Ana Ruiz (`c1`), CTO" in text
    assert "**20 seats** (`d1`): USD 4,800.00, New" in text and 'new deal "25 seats" (USD 6,000.00)' in text
    assert deals.calls.last.request.url.params["company_id"] == "co1"


def test_pipeline_summary(client):
    with respx.mock(base_url="https://api.test.com/v1") as api:
        api.get("/crm/pipelines").mock(return_value=Response(200, json=PIPELINES))
        api.get("/crm/deals/summary").mock(return_value=Response(200, json={
            "open_by_stage": [{"stage_name": "New", "currency": "USD", "count": 2, "amount": "1000"}],
            "forecast": [{"month": "2026-11", "currency": "USD", "count": 1, "amount": "1000", "weighted": "100"}],
            "period_days": 90, "won": 2, "lost": 1, "win_rate": 0.6667, "won_value": {"USD": "20"},
            "avg_cycle_days": 12.5, "overdue_count": 1, "overdue": [DEAL]}))
        text, err = call_tool(client, "deal_pipeline_summary", {})
    assert not err and "Sales (default) `p1`: New (10%) > Proposal (50%) > Won > Lost" in text
    assert "weighted USD 100.00" in text and "win rate 67%" in text and "Past their close date (1)" in text


def test_create_deal_resolves_stage_name_and_contact_company(client):
    with respx.mock(base_url="https://api.test.com/v1") as api:
        api.get("/crm/contacts/c1").mock(return_value=Response(200, json={"id": "c1", "company_id": "co1"}))
        api.get("/crm/pipelines").mock(return_value=Response(200, json=PIPELINES))
        create = api.post("/crm/deals").mock(return_value=Response(201, json={**DEAL, "stage_name": "Proposal"}))
        text, err = call_tool(client, "create_deal", {"name": "20 seats", "amount": 4800, "currency": "USD",
                                                      "contact_id": "c1", "stage": "proposal"})
        assert not err and 'Created deal "20 seats" (`d1`) in Proposal' in text
        assert json.loads(create.calls.last.request.content) == {
            "name": "20 seats", "amount": 4800, "currency": "USD", "primary_contact_id": "c1",
            "company_id": "co1", "stage_id": "s2"}
        text, err = call_tool(client, "create_deal", {"name": "x", "stage": "Signed"})
    assert err and "No stage called 'Signed'" in text and "New, Proposal" in text


def test_move_deal_and_errors(client):
    with respx.mock(base_url="https://api.test.com/v1") as api:
        api.get("/crm/deals/d1").mock(return_value=Response(200, json=DEAL))
        api.get("/crm/pipelines").mock(return_value=Response(200, json=PIPELINES))
        move = api.post("/crm/deals/d1/move").mock(return_value=Response(200, json={
            **DEAL, "stage_name": "Lost", "status": "lost"}))
        text, err = call_tool(client, "move_deal", {"deal_id": "d1", "stage": "Lost", "lost_reason": "No budget"})
    assert not err and '"20 seats" is now in Lost (lost)' in text
    assert json.loads(move.calls.last.request.content) == {"stage_id": "s4", "lost_reason": "No budget"}


def test_decide_suggestion(client):
    with respx.mock(base_url="https://api.test.com/v1") as api:
        accept = api.post("/crm/deal-suggestions/g1/accept").mock(return_value=Response(200, json={
            **SUGGESTION, "status": "accepted", "deal_id": "d9"}))
        api.post("/crm/deal-suggestions/g2/dismiss").mock(return_value=Response(200, json={
            **SUGGESTION, "id": "g2", "status": "dismissed"}))
        text, err = call_tool(client, "decide_deal_suggestion", {"suggestion_id": "g1", "decision": "accept",
                                                                 "amount": 5500})
        assert not err and 'Accepted "25 seats": created deal `d9`' in text
        assert json.loads(accept.calls.last.request.content) == {"amount": 5500}
        text, _ = call_tool(client, "decide_deal_suggestion", {"suggestion_id": "g2", "decision": "dismiss"})
        assert 'Dismissed the suggestion "25 seats"' in text
        text, err = call_tool(client, "decide_deal_suggestion", {"suggestion_id": "g2", "decision": "maybe"})
    assert err and "accept or dismiss" in text


def test_write_without_scope_is_explained(client):
    with respx.mock(base_url="https://api.test.com/v1") as api:
        api.post("/crm/deals").mock(return_value=Response(403, json={"detail": "Missing required scopes: write"}))
        text, err = call_tool(client, "create_deal", {"name": "x"})
    assert err and "write" in text
