"""AskBase MCP tools, defined once for both transports.

build_server() registers every tool on an MCPServer. The stdio entry point
(server.py) and the hosted HTTP app (http_server.py) both use it, so the
two can't drift apart.

API key resolution:
- Hosted (allow_env_key=False): only the caller's own key, from the
  X-API-Key header or "Authorization: Bearer <key>". There is no shared or
  default key, and no session state, so one caller can never act with
  another caller's key.
- Local stdio (allow_env_key=True): the ASK_API_KEY environment variable.
"""

from typing import Annotated, Any, Optional

import httpx
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from askbase_mcp.client import ASKClient
from askbase_mcp.config import Settings

INSTRUCTIONS = (
    "Tools for an AskBase knowledge base: search it, browse collections and "
    "documents, and add content. Answer from search results and cite the "
    "document title; if nothing relevant comes back, say the knowledge base "
    "doesn't cover it. CRM tools cover contacts, companies, deals and deal "
    "suggestions; confirm with the user before any tool that changes data."
)


class AskBaseError(ToolError):
    """A tool failure whose message is meant for the user (the SDK passes
    ToolError text through; other exceptions are masked as a crash)."""


def api_key_from_headers(headers) -> Optional[str]:
    """The caller's AskBase key from X-API-Key or a Bearer token."""
    if not headers:
        return None
    key = (headers.get("x-api-key") or "").strip()
    if key:
        return key
    auth = (headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def _explain(e: httpx.HTTPStatusError) -> str:
    code = e.response.status_code
    try:
        detail = e.response.json().get("detail")
    except Exception:
        detail = None
    if isinstance(detail, list):  # FastAPI validation errors
        detail = "; ".join(f"{'.'.join(map(str, d.get('loc', [])[1:]))}: {d.get('msg')}" for d in detail[:3])
    detail = f" ({detail})" if isinstance(detail, str) and detail else ""
    if code == 401:
        return "AskBase rejected the API key: check ASKBASE_API_KEY is set to a valid, active key." + detail
    if code == 403:
        return ("AskBase refused this action" + detail + ". Writes need an API key with the 'write' scope; "
                "CRM tools need CRM turned on for the project.")
    if code == 404:
        return "Not found in this AskBase project" + detail + "."
    return f"AskBase API error {code}{detail}."


def build_server(settings: Settings, *, allow_env_key: bool) -> MCPServer:
    server = MCPServer(
        name=settings.server_name,
        version=settings.server_version,
        instructions=INSTRUCTIONS,
    )

    async def call(ctx: Optional[Context], fn, *args, **kwargs) -> Any:
        key = api_key_from_headers(ctx.headers if ctx is not None else None)
        if not key and allow_env_key:
            key = settings.api_key
        if not key:
            raise AskBaseError("No AskBase API key. Set ASKBASE_API_KEY (sent as the X-API-Key header).")
        try:
            async with ASKClient(settings, api_key=key) as client:
                return await fn(client, *args, **kwargs)
        except httpx.HTTPStatusError as e:
            raise AskBaseError(_explain(e)) from None
        except httpx.RequestError:
            raise AskBaseError("Could not reach the AskBase API. Try again shortly.") from None

    @server.tool(description="Semantic search over the knowledge base. Returns the most relevant passages with their document titles and sources.")
    async def search(
        query: Annotated[str, Field(description="Natural-language question or keywords")],
        collection_ids: Annotated[Optional[list[str]], Field(description="Only search these collections (IDs)")] = None,
        top_k: Annotated[int, Field(ge=1, le=50, description="Number of results")] = 5,
        similarity_threshold: Annotated[Optional[float], Field(ge=0, le=1, description="Minimum similarity (0-1)")] = None,
        ctx: Optional[Context] = None,
    ) -> str:
        data = await call(ctx, lambda c: c.search(query, collection_ids, top_k, similarity_threshold))
        return format_search_results(data)

    @server.tool(description="List the knowledge base's collections.")
    async def list_collections(
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        ctx: Optional[Context] = None,
    ) -> str:
        return format_collections(await call(ctx, lambda c: c.list_collections(limit=limit)))

    @server.tool(description="Document, chunk and token counts for one collection.")
    async def get_collection_stats(
        collection_id: Annotated[str, Field(description="Collection ID")],
        ctx: Optional[Context] = None,
    ) -> str:
        return format_collection_stats(await call(ctx, lambda c: c.get_collection_stats(collection_id)))

    @server.tool(description="List documents, optionally in one collection or with one status (pending, processing, completed, failed).")
    async def list_documents(
        collection_id: Annotated[Optional[str], Field(description="Collection ID")] = None,
        status: Annotated[Optional[str], Field(description="pending, processing, completed or failed")] = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        ctx: Optional[Context] = None,
    ) -> str:
        return format_documents(await call(ctx, lambda c: c.list_documents(collection_id, status, limit=limit)))

    @server.tool(description="Details of one document.")
    async def get_document(
        document_id: Annotated[str, Field(description="Document ID")],
        ctx: Optional[Context] = None,
    ) -> str:
        return format_document(await call(ctx, lambda c: c.get_document(document_id)))

    @server.tool(description="The text chunks of one document, in order.")
    async def get_document_chunks(
        document_id: Annotated[str, Field(description="Document ID")],
        limit: Annotated[int, Field(ge=1, le=200)] = 50,
        ctx: Optional[Context] = None,
    ) -> str:
        return format_chunks(await call(ctx, lambda c: c.get_document_chunks(document_id, limit=limit)))

    @server.tool(description="Scrape one web page and add it to a collection.")
    async def ingest_url(
        url: Annotated[str, Field(description="Public http(s) URL")],
        collection_id: Annotated[str, Field(description="Collection ID")],
        title: Annotated[Optional[str], Field(description="Optional title")] = None,
        ctx: Optional[Context] = None,
    ) -> str:
        return format_ingestion_result(await call(ctx, lambda c: c.ingest_url(url, collection_id, title)))

    @server.tool(description="Crawl a website from a start URL and add its pages to a collection.")
    async def ingest_website(
        start_url: Annotated[str, Field(description="Public http(s) URL to start crawling from")],
        collection_id: Annotated[str, Field(description="Collection ID")],
        max_pages: Annotated[int, Field(ge=1, le=500)] = 50,
        url_pattern: Annotated[Optional[str], Field(description="Optional regex: only crawl matching URLs")] = None,
        ctx: Optional[Context] = None,
    ) -> str:
        return format_website_ingestion(
            await call(ctx, lambda c: c.ingest_website(start_url, collection_id, max_pages, url_pattern)))

    @server.tool(description="Add a text document to a collection.")
    async def create_document(
        collection_id: Annotated[str, Field(description="Collection ID")],
        content: Annotated[str, Field(description="The document text (markdown is fine)")],
        title: Annotated[Optional[str], Field(description="Document title")] = None,
        source_uri: Annotated[Optional[str], Field(description="Where the content came from")] = None,
        ctx: Optional[Context] = None,
    ) -> str:
        return format_document(
            await call(ctx, lambda c: c.create_document(collection_id, content, title, source_uri=source_uri)))

    @server.tool(description="Publish documents (or set them back to draft / unpublished). New documents start as drafts: only published documents are searchable and used by the live assistant, so publish after the user has reviewed them. Documents must have finished processing.")
    async def publish_documents(
        document_ids: Annotated[list[str], Field(min_length=1, description="Document IDs")],
        status: Annotated[str, Field(description="published (default), draft or unpublished")] = "published",
        ctx: Optional[Context] = None,
    ) -> str:
        if status not in ("published", "draft", "unpublished"):
            raise AskBaseError("status must be published, draft or unpublished.")
        async def apply(c: ASKClient) -> list[str]:
            lines = []
            for doc_id in document_ids:
                try:
                    d = await c.set_document_status(doc_id, status)
                    lines.append(f"- {d.get('title') or doc_id}: {d.get('publication_status', status)}")
                except httpx.HTTPStatusError as e:
                    lines.append(f"- `{doc_id}`: not changed. {_explain(e)}")
            return lines
        lines = await call(ctx, apply)
        return f"Set to {status}:\n" + "\n".join(lines)

    @server.tool(description="List the project's knowledge bases (each holds collections).")
    async def list_knowledge_bases(ctx: Optional[Context] = None) -> str:
        return format_knowledge_bases(await call(ctx, lambda c: c.list_knowledge_bases()))

    @server.tool(description="Create a collection. Collections live in a knowledge base: if the project has exactly one it's used, if it has none one is created; with several, pass knowledge_base_id. Needs an API key with the 'write' scope.")
    async def create_collection(
        name: Annotated[str, Field(description="Collection name")],
        description: Annotated[Optional[str], Field(description="What the collection holds")] = None,
        slug: Annotated[Optional[str], Field(description="URL-friendly id: lowercase letters, digits, hyphens (generated if omitted)")] = None,
        knowledge_base_id: Annotated[Optional[str], Field(description="Knowledge base to put it in (see list_knowledge_bases)")] = None,
        ctx: Optional[Context] = None,
    ) -> str:
        async def create(c: ASKClient):
            kb_id = knowledge_base_id
            created_kb = None
            if not kb_id:
                kbs = (await c.list_knowledge_bases()).get("knowledge_bases", [])
                if len(kbs) > 1:
                    names = ", ".join(f"{k['name']} (`{k['id']}`)" for k in kbs)
                    raise AskBaseError(f"This project has several knowledge bases; pass knowledge_base_id. Options: {names}")
                if kbs:
                    kb_id = kbs[0]["id"]
                else:
                    created_kb = await c.create_knowledge_base("Knowledge base", "Created by the AskBase plugin")
                    kb_id = created_kb["id"]
            col = await c.create_collection(name, slug, description, knowledge_base_id=kb_id)
            return col, created_kb
        col, created_kb = await call(ctx, create)
        text = format_collection_created(col)
        if created_kb:
            text += f"\n\n(Created knowledge base \"{created_kb['name']}\" to hold it.)"
        return text

    # ── Insights: questions the assistant couldn't answer ───

    @server.tool(description="Groups of customer questions the live assistant couldn't answer from the knowledge base, most frequent first. Use to find content gaps.")
    async def list_unanswered_questions(
        status: Annotated[str, Field(description="open, dismissed, resolved or all")] = "open",
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        ctx: Optional[Context] = None,
    ) -> str:
        return format_unanswered(await call(ctx, lambda c: c.list_missing_intents(status=status, limit=limit)))

    @server.tool(description="One group of unanswered questions: the real customer questions in it, and any saved answer suggestion.")
    async def get_unanswered_question(
        cluster_id: Annotated[str, Field(description="ID from list_unanswered_questions")],
        ctx: Optional[Context] = None,
    ) -> str:
        return format_unanswered_detail(await call(ctx, lambda c: c.get_missing_intent(cluster_id)))

    @server.tool(description="Have AskBase analyse a group of unanswered questions and recommend a fix: new content or flow, a new tool, or a data issue (uses the model; takes a few seconds).")
    async def suggest_answer(
        cluster_id: Annotated[str, Field(description="ID from list_unanswered_questions")],
        ctx: Optional[Context] = None,
    ) -> str:
        return format_suggestion(await call(ctx, lambda c: c.suggest_missing_intent(cluster_id)))

    @server.tool(description="Tool lookups (orders, accounts, bookings...) that came back empty for customers, grouped by pattern. Use to find integration or data gaps.")
    async def list_failed_lookups(
        status: Annotated[str, Field(description="open, dismissed, resolved or all")] = "open",
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        ctx: Optional[Context] = None,
    ) -> str:
        return format_failed_lookups(await call(ctx, lambda c: c.list_unresolved_lookups(status=status, limit=limit)))

    # ── CRM: contacts, memory, open items ───────────────────

    @server.tool(description="Find CRM contacts by name, email or company. Needs CRM turned on for the project.")
    async def find_contacts(
        query: Annotated[Optional[str], Field(description="Name, email or company to search for")] = None,
        stage: Annotated[Optional[str], Field(description="lead, active, inactive or churned")] = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 10,
        ctx: Optional[Context] = None,
    ) -> str:
        return format_contacts(await call(ctx, lambda c: c.list_contacts(search=query, stage=stage, limit=limit)))

    @server.tool(description="A CRM contact's profile: identity, company, stage, language, activity counts, tags and custom fields.")
    async def get_contact(
        contact_id: Annotated[str, Field(description="Contact ID from find_contacts")],
        ctx: Optional[Context] = None,
    ) -> str:
        return format_contact(await call(ctx, lambda c: c.get_contact(contact_id)))

    @server.tool(description="What the assistant remembers about a contact: current facts and preferences, open promises, recent conversation summaries and recent activity.")
    async def get_contact_memory(
        contact_id: Annotated[str, Field(description="Contact ID from find_contacts")],
        ctx: Optional[Context] = None,
    ) -> str:
        async def gather(c: ASKClient) -> dict:
            return {
                "cerebrum": await c.get_contact_cerebrum(contact_id),
                "open_loops": await c.get_contact_open_loops(contact_id, status="open"),
                "summaries": await c.get_contact_timeline_summaries(contact_id, limit=10),
                "activity": await c.get_contact_activity(contact_id, limit=10),
            }
        return format_contact_memory(await call(ctx, gather))

    @server.tool(description="Open items across all contacts: promises we made, things we're waiting on, follow-ups. Filter by owner and due date.")
    async def list_open_items(
        owner: Annotated[Optional[str], Field(description="us (we owe it) or customer (waiting on them)")] = None,
        due: Annotated[Optional[str], Field(description="overdue, this_week (next 7 days), later or no_date")] = None,
        status: Annotated[str, Field(description="open, done, cancelled or expired")] = "open",
        limit: Annotated[int, Field(ge=1, le=200)] = 50,
        ctx: Optional[Context] = None,
    ) -> str:
        return format_open_items(await call(ctx, lambda c: c.list_open_loops(status=status, owner=owner, due=due, limit=limit)))

    @server.tool(description="Mark an open item done or cancelled (or reopen it). Changes what the assistant tells the customer: confirm with the user first.")
    async def update_open_item(
        contact_id: Annotated[str, Field(description="The item's contact ID")],
        item_id: Annotated[str, Field(description="The open item ID")],
        status: Annotated[str, Field(description="done, cancelled or open")],
        note: Annotated[Optional[str], Field(description="Optional note on how it was resolved")] = None,
        ctx: Optional[Context] = None,
    ) -> str:
        if status not in ("done", "cancelled", "open"):
            raise AskBaseError("status must be done, cancelled or open.")
        r = await call(ctx, lambda c: c.update_open_loop(contact_id, item_id, status, note))
        return f"Open item \"{r['title']}\" is now {r['status']}."

    # ── CRM: companies, deals, suggestions ──────────────────

    @server.tool(description="Find companies in the CRM by name or email domain, optionally by industry or size. Shows contact counts and last activity.")
    async def find_companies(
        query: Annotated[Optional[str], Field(description="Name or domain to search for")] = None,
        industry: Annotated[Optional[str], Field(description="One of the project's industries")] = None,
        size: Annotated[Optional[str], Field(description="One of the project's company sizes")] = None,
        sort: Annotated[str, Field(description="name, contacts, recent or created")] = "name",
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        ctx: Optional[Context] = None,
    ) -> str:
        return format_companies(await call(ctx, lambda c: c.list_companies(query, industry, size, sort, limit)))

    @server.tool(description="A company's profile, its contacts, its open deals and any pending deal suggestions.")
    async def get_company(
        company_id: Annotated[str, Field(description="Company ID from find_companies or a contact")],
        ctx: Optional[Context] = None,
    ) -> str:
        async def gather(c: ASKClient) -> dict:
            company = await c.get_company(company_id)
            return {"company": company,
                    "deals": (await c.list_deals(company_id=company["id"], status="open", sort="close_date"))["deals"],
                    "suggestions": await c.list_deal_suggestions(company_id=company["id"])}
        return format_company(await call(ctx, gather))

    @server.tool(description="List deals. Filter by status (open, won, lost), pipeline, company, contact or name; sort by close_date, amount, updated, created or name.")
    async def list_deals(
        status: Annotated[Optional[str], Field(description="open, won or lost")] = "open",
        query: Annotated[Optional[str], Field(description="Text in the deal name")] = None,
        company_id: Annotated[Optional[str], Field(description="Only this company's deals")] = None,
        contact_id: Annotated[Optional[str], Field(description="Only deals this contact is on")] = None,
        pipeline_id: Annotated[Optional[str], Field(description="Only this pipeline")] = None,
        sort: Annotated[str, Field(description="close_date, amount, updated, created or name")] = "close_date",
        limit: Annotated[int, Field(ge=1, le=200)] = 50,
        ctx: Optional[Context] = None,
    ) -> str:
        return format_deals(await call(ctx, lambda c: c.list_deals(
            status=status, search=query, company_id=company_id, contact_id=contact_id, pipeline_id=pipeline_id,
            sort=sort, limit=limit)))

    @server.tool(description="One deal: amount, stage and probability, close date, company, people and their roles, at-risk flag, and recent history.")
    async def get_deal(
        deal_id: Annotated[str, Field(description="Deal ID from list_deals")],
        ctx: Optional[Context] = None,
    ) -> str:
        async def gather(c: ASKClient) -> dict:
            return {"deal": await c.get_deal(deal_id), "timeline": await c.get_deal_timeline(deal_id)}
        return format_deal(await call(ctx, gather))

    @server.tool(description="Pipeline overview: stages of each pipeline, open value by stage, weighted forecast by close month, win rate and average time to win over a period, and deals past their close date. Amounts are per currency, never converted.")
    async def deal_pipeline_summary(
        pipeline_id: Annotated[Optional[str], Field(description="Only this pipeline (default: all)")] = None,
        period_days: Annotated[int, Field(ge=1, le=730, description="Window for win rate and cycle")] = 90,
        ctx: Optional[Context] = None,
    ) -> str:
        async def gather(c: ASKClient) -> dict:
            return {"pipelines": await c.list_pipelines(), "summary": await c.deal_summary(pipeline_id, period_days)}
        return format_pipeline_summary(await call(ctx, gather))

    @server.tool(description="Deal suggestions the assistant noticed in customer conversations (new deal, move a deal forward, deal at risk), each with the customer's own words. Pending ones wait for a person to decide.")
    async def list_deal_suggestions(
        status: Annotated[str, Field(description="pending, accepted, dismissed or all")] = "pending",
        contact_id: Annotated[Optional[str], Field(description="Only this contact's")] = None,
        company_id: Annotated[Optional[str], Field(description="Only this company's")] = None,
        limit: Annotated[int, Field(ge=1, le=200)] = 50,
        ctx: Optional[Context] = None,
    ) -> str:
        return format_deal_suggestions(await call(ctx, lambda c: c.list_deal_suggestions(
            status, contact_id, company_id, limit)))

    async def _stage_id(c: ASKClient, stage: str, pipeline_id: Optional[str]) -> str:
        """A stage ID from an ID or a stage name (in the given or default pipeline)."""
        pipelines = await c.list_pipelines()
        stages = [s for p in pipelines for s in p["stages"]]
        if any(s["id"] == stage for s in stages):
            return stage
        scope = next((p for p in pipelines if p["id"] == pipeline_id), None) if pipeline_id else (
            pipelines[0] if pipelines else None)
        match = [s for s in (scope or {}).get("stages", []) if s["name"].lower() == stage.strip().lower()]
        if not match:
            names = ", ".join(s["name"] for s in (scope or {}).get("stages", []))
            raise AskBaseError(f"No stage called '{stage}'. Stages: {names}.")
        return match[0]["id"]

    @server.tool(description="Create a deal. Changes the CRM: confirm the details with the user first. Amounts need an ISO currency. Defaults to the default pipeline's first stage.")
    async def create_deal(
        name: Annotated[str, Field(description="Short deal name, e.g. '20 seats for Acme'")],
        amount: Annotated[Optional[float], Field(ge=0, description="Deal value")] = None,
        currency: Annotated[Optional[str], Field(description="ISO currency, e.g. USD (required with an amount)")] = None,
        expected_close_date: Annotated[Optional[str], Field(description="YYYY-MM-DD")] = None,
        contact_id: Annotated[Optional[str], Field(description="Main contact")] = None,
        company_id: Annotated[Optional[str], Field(description="Company (defaults to the contact's)")] = None,
        pipeline_id: Annotated[Optional[str], Field(description="Pipeline (default pipeline if omitted)")] = None,
        stage: Annotated[Optional[str], Field(description="Stage name or ID")] = None,
        ctx: Optional[Context] = None,
    ) -> str:
        async def run(c: ASKClient) -> dict:
            body: dict[str, Any] = {"name": name, "amount": amount, "currency": currency,
                                    "expected_close_date": expected_close_date, "primary_contact_id": contact_id,
                                    "company_id": company_id, "pipeline_id": pipeline_id}
            if contact_id and not company_id:
                body["company_id"] = (await c.get_contact(contact_id)).get("company_id")
            if stage:
                body["stage_id"] = await _stage_id(c, stage, pipeline_id)
            return await c.create_deal({k: v for k, v in body.items() if v is not None})
        d = await call(ctx, run)
        return f"Created deal \"{d['name']}\" (`{d['id']}`) in {d.get('stage_name')}: {_money(d.get('amount'), d.get('currency'))}."

    @server.tool(description="Move a deal to another stage (by name or ID); moving to a lost stage takes an optional reason. Changes the CRM: confirm with the user first.")
    async def move_deal(
        deal_id: Annotated[str, Field(description="Deal ID")],
        stage: Annotated[str, Field(description="Stage name (in the deal's pipeline) or stage ID")],
        lost_reason: Annotated[Optional[str], Field(description="Why it was lost, when moving to a lost stage")] = None,
        ctx: Optional[Context] = None,
    ) -> str:
        async def run(c: ASKClient) -> dict:
            deal = await c.get_deal(deal_id)
            return await c.move_deal(deal_id, await _stage_id(c, stage, deal["pipeline_id"]), lost_reason)
        d = await call(ctx, run)
        return f"\"{d['name']}\" is now in {d.get('stage_name')} ({d['status']})."

    @server.tool(description="Accept or dismiss a deal suggestion. Accepting a new_deal creates the deal (you can adjust name, amount, currency, close date); advance moves the deal; at_risk flags it. Confirm with the user first.")
    async def decide_deal_suggestion(
        suggestion_id: Annotated[str, Field(description="Suggestion ID from list_deal_suggestions")],
        decision: Annotated[str, Field(description="accept or dismiss")],
        name: Annotated[Optional[str], Field(description="new_deal: deal name to use")] = None,
        amount: Annotated[Optional[float], Field(ge=0, description="new_deal: amount to use")] = None,
        currency: Annotated[Optional[str], Field(description="new_deal: ISO currency")] = None,
        expected_close_date: Annotated[Optional[str], Field(description="new_deal: YYYY-MM-DD")] = None,
        ctx: Optional[Context] = None,
    ) -> str:
        if decision not in ("accept", "dismiss"):
            raise AskBaseError("decision must be accept or dismiss.")

        async def run(c: ASKClient) -> dict:
            if decision == "dismiss":
                return await c.dismiss_deal_suggestion(suggestion_id)
            body = {"name": name, "amount": amount, "currency": currency, "expected_close_date": expected_close_date}
            return await c.accept_deal_suggestion(suggestion_id, {k: v for k, v in body.items() if v is not None})
        s = await call(ctx, run)
        if s["status"] == "dismissed":
            return f"Dismissed the suggestion \"{s['title']}\"."
        done = {"new_deal": f"created deal `{s.get('deal_id')}`", "advance": f"moved {s.get('deal_name')}",
                "at_risk": f"flagged {s.get('deal_name')} as at risk"}[s["kind"]]
        return f"Accepted \"{s['title']}\": {done}."

    # ── Live assistant ──────────────────────────────────────

    @server.tool(description="Ask the project's live assistant a question, as an anonymous visitor would, and get its answer and sources. Each call runs the real model (costs tokens) and appears as a test conversation in the portal.")
    async def ask_assistant(
        question: Annotated[str, Field(description="The question, as a customer would ask it")],
        collection_ids: Annotated[Optional[list[str]], Field(description="Only use these collections")] = None,
        ctx: Optional[Context] = None,
    ) -> str:
        return format_assistant_answer(await call(ctx, lambda c: c.chat(question, collection_ids)))

    return server


# ── Formatting ───────────────────────────────────────────────


def format_search_results(data: dict) -> str:
    lines = [f"# Search results for: {data['query']}",
             f"{data['total_results']} results ({data['latency_ms']} ms)", ""]
    for i, r in enumerate(data["results"], 1):
        heading = f" › {r['heading']}" if r.get("heading") else ""
        lines += [f"## {i}. {r.get('document_title') or 'Untitled'}{heading} (score {r['score']:.2f})",
                  f"Source: {r.get('source_uri') or 'n/a'} · document `{r['document_id']}`", "",
                  r.get("content") or "[content not included]", "", "---"]
    if not data["results"]:
        lines.append("No results. Try different or broader keywords. (Search only covers published documents.)")
    return "\n".join(lines)


def format_collections(data: list) -> str:
    if not data:
        return "No collections yet."
    lines = ["# Collections", ""]
    for c in data:
        state = "active" if c.get("is_active", True) else "inactive"
        lines.append(f"- **{c['name']}** (`{c['id']}`), {c.get('document_count', 0)} documents, {state}")
        if c.get("description"):
            lines.append(f"  {c['description']}")
    return "\n".join(lines)


def format_collection_stats(data: dict) -> str:
    return (f"# Collection: {data['name']}\n\n- Documents: {data['document_count']}\n"
            f"- Chunks: {data['chunk_count']}\n- Tokens: {data['total_tokens']:,}")


def format_documents(data: list) -> str:
    if not data:
        return "No documents found."
    lines = ["# Documents", ""]
    for d in data:
        lines.append(f"- **{d.get('title') or 'Untitled'}** (`{d['id']}`): {d.get('publication_status', '?')}, "
                     f"processing {d['status']}, {d.get('chunk_count', 0)} chunks, "
                     f"updated {d.get('updated_at', d.get('created_at', '?'))}")
    return "\n".join(lines)


def format_document(data: dict) -> str:
    return (f"# {data.get('title') or 'Untitled document'}\n\n- ID: {data['id']}\n- Collection: {data['collection_id']}\n"
            f"- Processing: {data['status']}\n- Publication: {data.get('publication_status', '?')} "
            f"(only published documents are searchable and used by the assistant)\n"
            f"- Source: {data.get('source_uri') or 'n/a'}\n"
            f"- Chunks: {data.get('chunk_count', 0)}\n- Created: {data.get('created_at', '?')}")


def format_chunks(data: list) -> str:
    if not data:
        return "No chunks found."
    lines = [f"# Document chunks ({len(data)})", ""]
    for chunk in data:
        heading = f" › {chunk['heading']}" if chunk.get("heading") else ""
        lines += [f"## Chunk {chunk['chunk_index']}{heading}", chunk["content"], ""]
    return "\n".join(lines)


def format_ingestion_result(data: dict) -> str:
    if data.get("success") and data.get("document"):
        doc = data["document"]
        dup = " (already in the knowledge base)" if data.get("duplicate") else ""
        return (f"Ingested{dup}.\n\n- Document ID: {doc['document_id']}\n- Title: {doc['title']}\n"
                f"- Status: {doc['status']}\n- Chunks: {doc['chunk_count']}")
    return f"Ingestion failed: {data.get('error') or 'unknown error'}"


def format_knowledge_bases(data: dict) -> str:
    kbs = data.get("knowledge_bases", [])
    if not kbs:
        return "No knowledge bases yet. create_collection makes one when needed."
    return "# Knowledge bases\n\n" + "\n".join(
        f"- **{k['name']}** (`{k['id']}`): {k.get('collection_count', 0)} collections, {k.get('document_count', 0)} documents"
        for k in kbs)


def format_collection_created(data: dict) -> str:
    return f"Collection created.\n\n- ID: {data['id']}\n- Name: {data['name']}\n- Slug: {data['slug']}"


def format_website_ingestion(data: dict) -> str:
    lines = ["# Website ingestion", "", f"- Pages found: {data['total_pages_found']}",
             f"- Documents created: {data.get('documents_created', 0)}",
             f"- Processed: {data['documents_processed']}", f"- Failed: {data['documents_failed']}",
             f"- Skipped (unchanged): {data.get('documents_skipped', 0)}"]
    if data.get("errors"):
        lines += ["", "## Errors"] + [f"- {e}" for e in data["errors"][:5]]
    return "\n".join(lines)


def _when(value) -> str:
    return str(value)[:10] if value else "no date"


def format_unanswered(data: dict) -> str:
    items = data.get("items", [])
    if not items:
        return "No unanswered questions recorded."
    lines = [f"# Unanswered questions ({data.get('total', len(items))} groups)", ""]
    for i in items:
        label = i.get("cluster_label") or i["representative_query"]
        lines.append(f"- **{label}** (`{i['id']}`): asked {i['hit_count']}x by {i['member_count']} queries, "
                     f"last {_when(i['last_seen'])}, {i['status']}" + (", has suggestion" if i.get("has_suggestion") else ""))
        if i.get("cluster_label"):
            lines.append(f"  e.g. \"{i['representative_query']}\"")
    return "\n".join(lines)


def format_unanswered_detail(d: dict) -> str:
    lines = [f"# {d.get('cluster_label') or d['representative_query']}",
             f"Asked {d['hit_count']}x, {d['status']}, last {_when(d['last_seen'])}", "", "## Real questions"]
    for q in d.get("sample_queries", [])[:15]:
        lines.append(f"- {q.get('query') or q.get('text') or q}")
    if d.get("suggestion"):
        lines += ["", "## Saved suggestion", format_suggestion({"suggestion": d["suggestion"]})]
    return "\n".join(lines)


def format_suggestion(data: dict) -> str:
    """AskBase's suggestion: what kind of fix (new flow, extend a flow, new
    tool, or a data issue), why, and any missing tool methods."""
    sug = data.get("suggestion") or {}
    if not sug:
        return "No suggestion available."
    kinds = {"new_flow": "New conversational flow", "extend_flow": "Extend an existing flow",
             "new_tool": "New tool / integration", "data_issue": "Data or content issue"}
    lines = [f"**{sug.get('title', 'Suggestion')}** ({kinds.get(sug.get('recommendation_type'), sug.get('recommendation_type', '?'))})"]
    if sug.get("description"):
        lines.append(sug["description"])
    for m in sug.get("missing_methods") or []:
        lines.append(f"- missing tool `{m.get('tool_name')}`: {m.get('description', '')}")
    if sug.get("suggested_flow_outline"):
        lines += ["", "Flow outline:", str(sug["suggested_flow_outline"])]
    if sug.get("extend_flow_id"):
        lines.append(f"Flow to extend: `{sug['extend_flow_id']}`")
    return "\n".join(lines)


def format_failed_lookups(data: dict) -> str:
    items = data.get("items", [])
    if not items:
        return "No failed lookups recorded."
    lines = [f"# Failed lookups ({data.get('total', len(items))} patterns)", ""]
    for i in items:
        params = ", ".join(f"{k}={v}" for k, v in (i.get("param_pattern") or {}).items())
        lines.append(f"- **{i['tool_name']}**({params}) (`{i['id']}`): empty {i['hit_count']}x, last {_when(i['last_seen'])}")
    return "\n".join(lines)


def _name(c: dict) -> str:
    return " ".join(p for p in (c.get("first_name"), c.get("last_name")) if p) or c.get("email") or c.get("external_id") or "Unnamed"


def format_contacts(data: dict) -> str:
    contacts = data.get("contacts", [])
    if not contacts:
        return "No matching contacts."
    lines = [f"# Contacts ({data.get('total', len(contacts))})", ""]
    for c in contacts:
        extra = ", ".join(x for x in (c.get("email"), c.get("company_name") or c.get("company"), c.get("stage")) if x)
        lines.append(f"- **{_name(c)}** (`{c['id']}`): {extra}; {c.get('total_conversations', 0)} conversations, "
                     f"last seen {_when(c.get('last_seen_at'))}")
    return "\n".join(lines)


def format_contact(c: dict) -> str:
    lines = [f"# {_name(c)}", ""]
    if c.get("company_id"):
        lines.append(f"- Company: {c.get('company_name')} (`{c['company_id']}`)")
    for label, key in (("Email", "email"), ("Company", "company" if not c.get("company_id") else ""), ("Job title", "job_title"), ("Stage", "stage"),
                       ("Language", "preferred_language"), ("Country", "country_name"), ("Time zone", "timezone_code"),
                       ("Source", "source")):
        if c.get(key):
            lines.append(f"- {label}: {c[key]}")
    lines.append(f"- Conversations: {c.get('total_conversations', 0)}, messages: {c.get('total_messages', 0)}, "
                 f"first seen {_when(c.get('first_seen_at'))}, last seen {_when(c.get('last_seen_at'))}")
    if c.get("last_activity_summary"):
        lines.append(f"- Last activity: {c['last_activity_summary']}")
    if c.get("tags"):
        lines.append("- Tags: " + ", ".join(c["tags"]))
    if c.get("custom_fields"):
        lines.append("- Custom fields: " + ", ".join(f"{k}={v}" for k, v in c["custom_fields"].items()))
    return "\n".join(lines)


def format_contact_memory(m: dict) -> str:
    lines = ["# What the assistant remembers", ""]
    facts = [e for e in m["cerebrum"] if e.get("is_active", True) and not e.get("valid_to")]
    sections = {"preference": "Preferences", "fact": "Facts", "decision": "Decisions", "do_not_repeat": "Do not repeat"}
    for key, title in sections.items():
        items = [e for e in facts if e.get("section") == key]
        if items:
            lines.append(f"## {title}")
            lines += [f"- {e['content']}" for e in items]
            lines.append("")
    if not facts:
        lines += ["No stored facts or preferences.", ""]
    lines.append("## Open items")
    if m["open_loops"]:
        for o in m["open_loops"]:
            who = "we owe" if o["owner"] == "us" else "waiting on them"
            lines.append(f"- {o['title']} ({who}, due {_when(o.get('due_at'))})")
    else:
        lines.append("- None")
    lines += ["", "## Recent conversation summaries"]
    if m["summaries"]:
        lines += [f"- {s['period_key']} ({s['period']}): {s['summary']}" for s in m["summaries"]]
    else:
        lines.append("- None yet")
    if m["activity"]:
        lines += ["", "## Recent activity"]
        for a in m["activity"]:
            lines.append(f"- {_when(a.get('created_at'))} {a.get('entry_type')}: {(a.get('content') or a.get('type') or '')[:200]}")
    return "\n".join(lines)


def format_open_items(data: dict) -> str:
    items, counts = data.get("items", []), data.get("counts") or {}
    lines = [f"# Open items: {counts.get('open', len(items))} open, {counts.get('overdue', 0)} overdue, "
             f"{counts.get('due_this_week', 0)} due in 7 days, {counts.get('waiting_on_customer', 0)} waiting on customers", ""]
    if not items:
        return lines[0] + "\n\nNothing matches."
    for i in items:
        who = "we owe" if i["owner"] == "us" else "waiting on them"
        contact = i.get("contact_name") or i.get("contact_email") or "unnamed contact"
        lines.append(f"- **{i['title']}** for {contact} ({who}, due {_when(i.get('due_at'))}) "
                     f"item `{i['id']}`, contact `{i['contact_id']}`")
    return "\n".join(lines)


def format_assistant_answer(r: dict) -> str:
    lines = ["# Assistant answer", "", r.get("response", ""), "", f"_model {r.get('model', '?')}, {r.get('latency_ms', '?')} ms_"]
    sources = r.get("sources") or []
    if sources:
        lines += ["", "## Sources used"] + [f"- {s.get('document_title') or 'Untitled'} (score {s.get('score', 0):.2f})"
                                           for s in sources[:8]]
    else:
        lines += ["", "No knowledge-base sources were used."]
    return "\n".join(lines)


# ── CRM: companies and deals ─────────────────────────────────


def _money(amount, currency) -> str:
    if amount in (None, ""):
        return "no amount"
    try:
        value = f"{float(amount):,.2f}"
    except (TypeError, ValueError):
        value = str(amount)
    return f"{currency or ''} {value}".strip()


def _totals(totals: dict) -> str:
    return ", ".join(_money(v, k) for k, v in totals.items()) or "no amounts"


def format_companies(data: dict) -> str:
    companies = data.get("companies", [])
    if not companies:
        return "No matching companies."
    lines = [f"# Companies ({data.get('total', len(companies))})", ""]
    for c in companies:
        extra = ", ".join(x for x in (c.get("domain"), c.get("industry"), c.get("size")) if x)
        n = c.get("contact_count", 0)
        lines.append(f"- **{c['name']}** (`{c['id']}`){': ' + extra if extra else ''}; {n} "
                     f"contact{'' if n == 1 else 's'}, last active {_when(c.get('last_seen_at'))}")
    return "\n".join(lines)


def _deal_line(d: dict) -> str:
    who = ", ".join(x for x in (d.get("company_name"), d.get("primary_contact_name")) if x)
    risk = " **at risk**" if d.get("at_risk_since") else ""
    close = f", closes {_when(d['expected_close_date'])}" if d.get("expected_close_date") else ""
    return (f"- **{d['name']}** (`{d['id']}`): {_money(d.get('amount'), d.get('currency'))}, {d.get('stage_name') or d['status']}"
            f"{close}{' - ' + who if who else ''}{risk}")


def format_company(m: dict) -> str:
    c = m["company"]
    lines = [f"# {c['name']}", ""]
    for label, key in (("Domain", "domain"), ("Website", "website"), ("Industry", "industry"), ("Size", "size"),
                       ("Country", "country_name"), ("Description", "description")):
        if c.get(key):
            lines.append(f"- {label}: {c[key]}")
    if c.get("tags"):
        lines.append("- Tags: " + ", ".join(c["tags"]))
    lines += ["", f"## Contacts ({c.get('contact_count', 0)})"]
    lines += [f"- {_name(p)} (`{p['id']}`){', ' + p['job_title'] if p.get('job_title') else ''}, "
              f"last seen {_when(p.get('last_seen_at'))}" for p in (c.get("contacts") or [])] or ["- None"]
    lines += ["", "## Open deals"] + ([_deal_line(d) for d in m["deals"]] or ["- None"])
    if m["suggestions"]:
        lines += ["", "## Pending deal suggestions"] + [_suggestion_line(s) for s in m["suggestions"]]
    return "\n".join(lines)


def format_deals(data: dict) -> str:
    deals = data.get("deals", [])
    if not deals:
        return "No matching deals."
    return "\n".join([f"# Deals ({data.get('total', len(deals))})", ""] + [_deal_line(d) for d in deals])


def format_deal(m: dict) -> str:
    d = m["deal"]
    lines = [f"# {d['name']}", "",
             f"- Value: {_money(d.get('amount'), d.get('currency'))}",
             f"- Stage: {d.get('stage_name')} ({d['status']}"
             + (f", {d.get('probability')}% win probability)" if d["status"] == "open" else ")"),
             f"- Expected close: {_when(d.get('expected_close_date'))}"]
    if d.get("company_id"):
        lines.append(f"- Company: {d.get('company_name')} (`{d['company_id']}`)")
    for p in d.get("contacts") or []:
        main = " (main contact)" if p["contact_id"] == d.get("primary_contact_id") else ""
        lines.append(f"- Person: {p.get('name') or p.get('email')} (`{p['contact_id']}`), {p['role'].replace('_', ' ')}{main}")
    if d.get("at_risk_since"):
        lines.append(f"- **At risk** since {_when(d['at_risk_since'])}: \"{d.get('at_risk_reason') or ''}\"")
    if d["status"] == "lost" and d.get("lost_reason"):
        lines.append(f"- Lost because: {d['lost_reason']}")
    lines.append(f"- Source: {d.get('source')}, created {_when(d.get('created_at'))}")
    if m["timeline"]:
        lines += ["", "## Recent history"]
        lines += [f"- {_when(e.get('created_at'))} {e.get('entry_type')}: {(e.get('content') or e.get('type') or '')[:200]}"
                  for e in m["timeline"]]
    return "\n".join(lines)


def format_pipeline_summary(m: dict) -> str:
    s = m["summary"]
    lines = ["# Pipeline summary", "", "## Pipelines"]
    for p in m["pipelines"]:
        stages = " > ".join(f"{st['name']} ({st['probability']}%)" if st["kind"] == "open" else st["name"]
                            for st in p["stages"])
        lines.append(f"- {p['name']}{' (default)' if p.get('is_default') else ''} `{p['id']}`: {stages}")
    lines += ["", "## Open deals by stage"]
    lines += [f"- {r['stage_name']}: {r['count']} deal(s), {_money(r['amount'], r['currency']) if r.get('currency') else 'no amount'}"
              for r in s["open_by_stage"]] or ["- None"]
    lines += ["", "## Forecast by close month (weighted = amount x stage probability)"]
    lines += [f"- {f['month']}: {f['count']} deal(s), {_money(f['amount'], f['currency'])}, weighted {_money(f['weighted'], f['currency'])}"
              for f in s["forecast"]] or ["- No open deals with a close date and amount"]
    rate = f"{round(s['win_rate'] * 100)}%" if s.get("win_rate") is not None else "n/a"
    cycle = f"{s['avg_cycle_days']} days" if s.get("avg_cycle_days") is not None else "n/a"
    lines += ["", f"## Last {s['period_days']} days",
              f"- Won {s['won']}, lost {s['lost']}, win rate {rate}, average time to win {cycle}",
              f"- Won value: {_totals(s.get('won_value') or {})}",
              "", f"## Past their close date ({s['overdue_count']})"]
    lines += [_deal_line(d) for d in s["overdue"]] or ["- None"]
    return "\n".join(lines)


def _suggestion_line(s: dict) -> str:
    what = {"new_deal": f"new deal \"{s['title']}\"",
            "advance": f"move {s.get('deal_name')} to {s.get('suggested_stage_name') or 'the next stage'}",
            "at_risk": f"{s.get('deal_name')} at risk"}.get(s["kind"], s["kind"])
    money = f" ({_money(s['amount'], s['currency'])})" if s.get("amount") else ""
    return (f"- {what}{money} for {s.get('contact_name') or 'a contact'}: \"{s['evidence']}\" "
            f"[{s['status']}, {_when(s.get('created_at'))}] `{s['id']}`")


def format_deal_suggestions(items: list) -> str:
    if not items:
        return "No deal suggestions."
    return "\n".join([f"# Deal suggestions ({len(items)})", ""] + [_suggestion_line(s) for s in items])
