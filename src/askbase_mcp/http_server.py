"""HTTP SSE transport for ASKbase MCP Server.

This module provides an HTTP server that speaks the MCP protocol over
Server-Sent Events (SSE), suitable for deployment to Cloud Run.

API keys can be provided via:
1. Environment variable ASK_API_KEY (server-wide default)
2. X-API-Key header in requests (per-customer)
3. api_key query parameter (per-customer)
"""

import asyncio
import json
import logging
from typing import Any, Optional

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from sse_starlette.sse import EventSourceResponse

from askbase_mcp.config import get_settings, Settings
from askbase_mcp.client import ASKClient

logger = logging.getLogger(__name__)


def get_api_key_from_request(request: Request, default_key: str = "") -> str:
    """Extract API key from request headers, query params, or use default."""
    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        return api_key
    api_key = request.query_params.get("api_key", "")
    if api_key:
        return api_key
    return default_key


# Tool definitions
TOOLS = [
    {
        "name": "search",
        "description": "Perform semantic search over your knowledge base. Returns the most relevant document chunks based on vector similarity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query (natural language question or keywords)"},
                "collection_ids": {"type": "array", "items": {"type": "string", "format": "uuid"}, "description": "Optional: Limit search to specific collection IDs"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 100, "default": 5, "description": "Number of results to return"},
                "similarity_threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.4, "description": "Minimum similarity score (0-1)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_collections",
        "description": "List all available document collections in your knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20, "description": "Maximum number of collections to return"},
            },
        },
    },
    {
        "name": "get_collection_stats",
        "description": "Get statistics for a specific collection (document count, chunk count, total tokens).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "collection_id": {"type": "string", "format": "uuid", "description": "The collection ID"},
            },
            "required": ["collection_id"],
        },
    },
    {
        "name": "list_documents",
        "description": "List documents, optionally filtered by collection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "collection_id": {"type": "string", "format": "uuid", "description": "Optional: Filter by collection ID"},
                "status": {"type": "string", "enum": ["pending", "processing", "completed", "failed"], "description": "Optional: Filter by processing status"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
        },
    },
    {
        "name": "get_document",
        "description": "Get details for a specific document.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "format": "uuid", "description": "The document ID"},
            },
            "required": ["document_id"],
        },
    },
    {
        "name": "get_document_chunks",
        "description": "Get the text chunks for a specific document.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "format": "uuid", "description": "The document ID"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            },
            "required": ["document_id"],
        },
    },
    {
        "name": "ingest_url",
        "description": "Scrape and ingest content from a URL into your knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "format": "uri", "description": "The URL to scrape and ingest"},
                "collection_id": {"type": "string", "format": "uuid", "description": "Target collection ID"},
                "title": {"type": "string", "description": "Optional: Override the page title"},
            },
            "required": ["url", "collection_id"],
        },
    },
    {
        "name": "create_document",
        "description": "Create a new text document in your knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "collection_id": {"type": "string", "format": "uuid", "description": "Target collection ID"},
                "content": {"type": "string", "description": "The text content of the document"},
                "title": {"type": "string", "description": "Document title"},
                "source_uri": {"type": "string", "description": "Optional: Source URI for reference"},
            },
            "required": ["collection_id", "content"],
        },
    },
    {
        "name": "create_collection",
        "description": "Create a new document collection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Collection name"},
                "description": {"type": "string", "description": "Optional: Collection description"},
                "slug": {"type": "string", "pattern": "^[a-z0-9-]+$", "description": "Optional: URL-friendly slug"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "ingest_website",
        "description": "Crawl and ingest an entire website (follows internal links).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_url": {"type": "string", "format": "uri", "description": "Starting URL for the crawl"},
                "collection_id": {"type": "string", "format": "uuid", "description": "Target collection ID"},
                "max_pages": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50, "description": "Maximum pages to crawl"},
                "url_pattern": {"type": "string", "description": "Optional: Regex pattern to filter URLs"},
            },
            "required": ["start_url", "collection_id"],
        },
    },
]


class MCPHTTPHandler:
    """Handles MCP protocol over HTTP/SSE."""

    def __init__(self):
        self.base_settings = get_settings()
        self._sessions: dict[str, dict] = {}

    def _get_settings_for_request(self, request: Request) -> Settings:
        """Create settings with API key from request."""
        api_key = get_api_key_from_request(request, self.base_settings.api_key)
        return Settings(
            api_key=api_key,
            api_base_url=self.base_settings.api_base_url,
            default_similarity_threshold=self.base_settings.default_similarity_threshold,
        )

    async def handle_sse(self, request: Request) -> EventSourceResponse:
        """Handle SSE connection for MCP messages."""
        session_id = request.query_params.get("session_id", "default")
        settings = self._get_settings_for_request(request)

        queue: asyncio.Queue = asyncio.Queue()
        self._sessions[session_id] = {"queue": queue, "settings": settings}

        async def event_generator():
            try:
                yield {"event": "endpoint", "data": json.dumps({"url": f"/mcp/message?session_id={session_id}"})}
                while True:
                    try:
                        message = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield {"event": "message", "data": json.dumps(message)}
                    except asyncio.TimeoutError:
                        yield {"event": "ping", "data": ""}
            except asyncio.CancelledError:
                pass
            finally:
                self._sessions.pop(session_id, None)

        return EventSourceResponse(event_generator())

    async def handle_message(self, request: Request) -> JSONResponse:
        """Handle incoming MCP JSON-RPC message."""
        session_id = request.query_params.get("session_id", "default")

        try:
            body = await request.json()
            logger.debug(f"Received message: {body}")

            settings = self._sessions.get(session_id, {}).get("settings") or self._get_settings_for_request(request)
            response = await self._process_jsonrpc(body, settings)

            if session_id in self._sessions:
                await self._sessions[session_id]["queue"].put(response)

            return JSONResponse(response)

        except Exception as e:
            logger.exception("Error processing message")
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": body.get("id") if isinstance(body, dict) else None,
                "error": {"code": -32603, "message": str(e)}
            }, status_code=500)

    async def _process_jsonrpc(self, request: dict, settings: Settings) -> dict:
        """Process a JSON-RPC request and return response."""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": self.base_settings.server_name, "version": self.base_settings.server_version}
                }
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                content = await self._call_tool(tool_name, tool_args, settings)
                result = {"content": content}
            elif method == "notifications/initialized":
                return {"jsonrpc": "2.0", "id": request_id, "result": {}}
            else:
                return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}

            return {"jsonrpc": "2.0", "id": request_id, "result": result}

        except Exception as e:
            logger.exception(f"Error processing {method}")
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": str(e)}}

    async def _call_tool(self, name: str, arguments: dict, settings: Settings) -> list[dict]:
        """Execute a tool and return content."""
        async with ASKClient(settings) as client:
            if name == "search":
                result = await client.search(
                    query=arguments["query"],
                    collection_ids=arguments.get("collection_ids"),
                    top_k=arguments.get("top_k"),
                    similarity_threshold=arguments.get("similarity_threshold"),
                )
                return [{"type": "text", "text": self._format_search_results(result)}]

            elif name == "list_collections":
                result = await client.list_collections(limit=arguments.get("limit", 20))
                return [{"type": "text", "text": self._format_collections(result)}]

            elif name == "get_collection_stats":
                result = await client.get_collection_stats(arguments["collection_id"])
                return [{"type": "text", "text": self._format_collection_stats(result)}]

            elif name == "list_documents":
                result = await client.list_documents(
                    collection_id=arguments.get("collection_id"),
                    status=arguments.get("status"),
                    limit=arguments.get("limit", 20),
                )
                return [{"type": "text", "text": self._format_documents(result)}]

            elif name == "get_document":
                result = await client.get_document(arguments["document_id"])
                return [{"type": "text", "text": self._format_document(result)}]

            elif name == "get_document_chunks":
                result = await client.get_document_chunks(arguments["document_id"], limit=arguments.get("limit", 50))
                return [{"type": "text", "text": self._format_chunks(result)}]

            elif name == "ingest_url":
                result = await client.ingest_url(
                    url=arguments["url"],
                    collection_id=arguments["collection_id"],
                    title=arguments.get("title"),
                )
                return [{"type": "text", "text": self._format_ingestion_result(result)}]

            elif name == "create_document":
                result = await client.create_document(
                    collection_id=arguments["collection_id"],
                    content=arguments["content"],
                    title=arguments.get("title"),
                    source_uri=arguments.get("source_uri"),
                )
                return [{"type": "text", "text": self._format_document(result)}]

            elif name == "create_collection":
                result = await client.create_collection(
                    name=arguments["name"],
                    description=arguments.get("description"),
                    slug=arguments.get("slug"),
                )
                return [{"type": "text", "text": self._format_collection_created(result)}]

            elif name == "ingest_website":
                result = await client.ingest_website(
                    start_url=arguments["start_url"],
                    collection_id=arguments["collection_id"],
                    max_pages=arguments.get("max_pages", 50),
                    url_pattern=arguments.get("url_pattern"),
                )
                return [{"type": "text", "text": self._format_website_ingestion(result)}]

            else:
                return [{"type": "text", "text": f"Unknown tool: {name}"}]

    # Formatting helpers
    def _format_search_results(self, data: dict) -> str:
        lines = [f"# Search Results for: {data['query']}", f"Found {data['total_results']} results (latency: {data['latency_ms']}ms)", ""]
        for i, result in enumerate(data["results"], 1):
            lines.extend([
                f"## Result {i} (score: {result['score']:.3f})",
                f"**Document:** {result.get('document_title', 'Untitled')}",
                f"**Source:** {result.get('source_uri', 'None')}",
                "",
                result.get("content", "[Content not included]"),
                "",
                "---",
            ])
        if not data["results"]:
            lines.append("No results found. Try broadening your search query.")
        return "\n".join(lines)

    def _format_collections(self, data: list) -> str:
        if not data:
            return "No collections found."
        lines = ["# Collections", ""]
        for c in data:
            status = "active" if c.get("is_active", True) else "inactive"
            lines.append(f"- **{c['name']}** (`{c['id']}`) - {status}")
            if c.get("description"):
                lines.append(f"  {c['description']}")
        return "\n".join(lines)

    def _format_collection_stats(self, data: dict) -> str:
        return f"# Collection: {data['name']}\n\n- **Documents:** {data['document_count']}\n- **Chunks:** {data['chunk_count']}\n- **Total Tokens:** {data['total_tokens']:,}"

    def _format_documents(self, data: list) -> str:
        if not data:
            return "No documents found."
        lines = ["# Documents", ""]
        for d in data:
            lines.append(f"- **{d.get('title', 'Untitled')}** (`{d['id']}`)")
            lines.append(f"  Status: {d['status']} | Chunks: {d.get('chunk_count', 0)}")
        return "\n".join(lines)

    def _format_document(self, data: dict) -> str:
        return f"# {data.get('title', 'Untitled Document')}\n\n- **ID:** {data['id']}\n- **Collection:** {data['collection_id']}\n- **Status:** {data['status']}\n- **Source:** {data.get('source_uri', 'N/A')}\n- **Chunks:** {data.get('chunk_count', 0)}\n- **Created:** {data['created_at']}"

    def _format_chunks(self, data: list) -> str:
        if not data:
            return "No chunks found."
        lines = [f"# Document Chunks ({len(data)} chunks)", ""]
        for chunk in data:
            heading = f" - {chunk['heading']}" if chunk.get('heading') else ""
            lines.extend([f"## Chunk {chunk['chunk_index']}{heading}", chunk['content'], ""])
        return "\n".join(lines)

    def _format_ingestion_result(self, data: dict) -> str:
        if data.get("success"):
            doc = data["document"]
            return f"Successfully ingested URL!\n\n- **Document ID:** {doc['document_id']}\n- **Title:** {doc['title']}\n- **Status:** {doc['status']}\n- **Chunks:** {doc['chunk_count']}\n- **Tokens:** {doc['total_tokens']}"
        return f"Ingestion failed: {data.get('error', 'Unknown error')}"

    def _format_collection_created(self, data: dict) -> str:
        return f"Collection created!\n\n- **ID:** {data['id']}\n- **Name:** {data['name']}\n- **Slug:** {data['slug']}"

    def _format_website_ingestion(self, data: dict) -> str:
        lines = ["# Website Ingestion Results", "", f"- **Success:** {data['success']}", f"- **Pages Found:** {data['total_pages_found']}", f"- **Documents Processed:** {data['documents_processed']}", f"- **Documents Failed:** {data['documents_failed']}"]
        if data.get("errors"):
            lines.extend(["", "## Errors:"])
            for error in data["errors"][:5]:
                lines.append(f"- {error}")
        return "\n".join(lines)

    async def health_check(self, request: Request) -> JSONResponse:
        """Health check endpoint for Cloud Run."""
        return JSONResponse({
            "status": "healthy",
            "server": self.base_settings.server_name,
            "version": self.base_settings.server_version
        })


def create_app() -> Starlette:
    """Create the Starlette application."""
    handler = MCPHTTPHandler()
    routes = [
        Route("/health", handler.health_check, methods=["GET"]),
        Route("/mcp/sse", handler.handle_sse, methods=["GET"]),
        Route("/mcp/message", handler.handle_message, methods=["POST"]),
        Route("/mcp", handler.handle_message, methods=["POST"]),
    ]
    return Starlette(routes=routes)


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
