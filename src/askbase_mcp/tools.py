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
    "doesn't cover it."
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
    detail = f" ({detail})" if isinstance(detail, str) else ""
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

    @server.tool(description="Create a collection. Needs an API key with the 'write' scope.")
    async def create_collection(
        name: Annotated[str, Field(description="Collection name")],
        description: Annotated[Optional[str], Field(description="What the collection holds")] = None,
        slug: Annotated[Optional[str], Field(description="URL-friendly id (generated if omitted)")] = None,
        ctx: Optional[Context] = None,
    ) -> str:
        return format_collection_created(await call(ctx, lambda c: c.create_collection(name, slug, description)))

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
        lines.append("No results. Try different or broader keywords.")
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
        lines.append(f"- **{d.get('title') or 'Untitled'}** (`{d['id']}`): {d['status']}, "
                     f"{d.get('chunk_count', 0)} chunks, updated {d.get('updated_at', d.get('created_at', '?'))}")
    return "\n".join(lines)


def format_document(data: dict) -> str:
    return (f"# {data.get('title') or 'Untitled document'}\n\n- ID: {data['id']}\n- Collection: {data['collection_id']}\n"
            f"- Status: {data['status']}\n- Source: {data.get('source_uri') or 'n/a'}\n"
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
