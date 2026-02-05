"""ASKbase MCP Server implementation."""

import asyncio
import logging
from typing import Any

from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import stdio_server

from askbase_mcp.config import get_settings, Settings
from askbase_mcp.client import ASKClient

logger = logging.getLogger(__name__)


def create_server(settings: Settings) -> Server:
    """Create and configure the MCP server."""
    server = Server(settings.server_name)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Return list of available tools."""
        return [
            Tool(
                name="search",
                description=(
                    "Perform semantic search over your knowledge base. "
                    "Returns the most relevant document chunks based on vector similarity."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query (natural language question or keywords)",
                        },
                        "collection_ids": {
                            "type": "array",
                            "items": {"type": "string", "format": "uuid"},
                            "description": "Optional: Limit search to specific collection IDs",
                        },
                        "top_k": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                            "default": 5,
                            "description": "Number of results to return",
                        },
                        "similarity_threshold": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                            "default": 0.7,
                            "description": "Minimum similarity score (0-1)",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="list_collections",
                description="List all available document collections in your knowledge base.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                            "default": 20,
                            "description": "Maximum number of collections to return",
                        },
                    },
                },
            ),
            Tool(
                name="get_collection_stats",
                description="Get statistics for a specific collection (document count, chunk count, total tokens).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "collection_id": {
                            "type": "string",
                            "format": "uuid",
                            "description": "The collection ID",
                        },
                    },
                    "required": ["collection_id"],
                },
            ),
            Tool(
                name="list_documents",
                description="List documents, optionally filtered by collection.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "collection_id": {
                            "type": "string",
                            "format": "uuid",
                            "description": "Optional: Filter by collection ID",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "processing", "completed", "failed"],
                            "description": "Optional: Filter by processing status",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                            "default": 20,
                        },
                    },
                },
            ),
            Tool(
                name="get_document",
                description="Get details for a specific document.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "document_id": {
                            "type": "string",
                            "format": "uuid",
                            "description": "The document ID",
                        },
                    },
                    "required": ["document_id"],
                },
            ),
            Tool(
                name="get_document_chunks",
                description="Get the text chunks for a specific document.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "document_id": {
                            "type": "string",
                            "format": "uuid",
                            "description": "The document ID",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 200,
                            "default": 50,
                        },
                    },
                    "required": ["document_id"],
                },
            ),
            Tool(
                name="ingest_url",
                description="Scrape and ingest content from a URL into your knowledge base.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "format": "uri",
                            "description": "The URL to scrape and ingest",
                        },
                        "collection_id": {
                            "type": "string",
                            "format": "uuid",
                            "description": "Target collection ID",
                        },
                        "title": {
                            "type": "string",
                            "description": "Optional: Override the page title",
                        },
                    },
                    "required": ["url", "collection_id"],
                },
            ),
            Tool(
                name="create_document",
                description="Create a new text document in your knowledge base.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "collection_id": {
                            "type": "string",
                            "format": "uuid",
                            "description": "Target collection ID",
                        },
                        "content": {
                            "type": "string",
                            "description": "The text content of the document",
                        },
                        "title": {
                            "type": "string",
                            "description": "Document title",
                        },
                        "source_uri": {
                            "type": "string",
                            "description": "Optional: Source URI for reference",
                        },
                    },
                    "required": ["collection_id", "content"],
                },
            ),
            Tool(
                name="create_collection",
                description="Create a new document collection.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Collection name",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional: Collection description",
                        },
                        "slug": {
                            "type": "string",
                            "pattern": "^[a-z0-9-]+$",
                            "description": "Optional: URL-friendly slug",
                        },
                    },
                    "required": ["name"],
                },
            ),
            Tool(
                name="ingest_website",
                description="Crawl and ingest an entire website (follows internal links).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "start_url": {
                            "type": "string",
                            "format": "uri",
                            "description": "Starting URL for the crawl",
                        },
                        "collection_id": {
                            "type": "string",
                            "format": "uuid",
                            "description": "Target collection ID",
                        },
                        "max_pages": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 200,
                            "default": 50,
                            "description": "Maximum pages to crawl",
                        },
                        "url_pattern": {
                            "type": "string",
                            "description": "Optional: Regex pattern to filter URLs",
                        },
                    },
                    "required": ["start_url", "collection_id"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Handle tool execution."""
        try:
            async with ASKClient(settings) as client:
                if name == "search":
                    result = await client.search(
                        query=arguments["query"],
                        collection_ids=arguments.get("collection_ids"),
                        top_k=arguments.get("top_k"),
                        similarity_threshold=arguments.get("similarity_threshold"),
                    )
                    return _format_search_results(result)

                elif name == "list_collections":
                    result = await client.list_collections(
                        limit=arguments.get("limit", 20),
                    )
                    return _format_collections(result)

                elif name == "get_collection_stats":
                    result = await client.get_collection_stats(
                        collection_id=arguments["collection_id"],
                    )
                    return _format_collection_stats(result)

                elif name == "list_documents":
                    result = await client.list_documents(
                        collection_id=arguments.get("collection_id"),
                        status=arguments.get("status"),
                        limit=arguments.get("limit", 20),
                    )
                    return _format_documents(result)

                elif name == "get_document":
                    result = await client.get_document(
                        document_id=arguments["document_id"],
                    )
                    return _format_document(result)

                elif name == "get_document_chunks":
                    result = await client.get_document_chunks(
                        document_id=arguments["document_id"],
                        limit=arguments.get("limit", 50),
                    )
                    return _format_chunks(result)

                elif name == "ingest_url":
                    result = await client.ingest_url(
                        url=arguments["url"],
                        collection_id=arguments["collection_id"],
                        title=arguments.get("title"),
                    )
                    return _format_ingestion_result(result)

                elif name == "create_document":
                    result = await client.create_document(
                        collection_id=arguments["collection_id"],
                        content=arguments["content"],
                        title=arguments.get("title"),
                        source_uri=arguments.get("source_uri"),
                    )
                    return _format_document(result)

                elif name == "create_collection":
                    result = await client.create_collection(
                        name=arguments["name"],
                        description=arguments.get("description"),
                        slug=arguments.get("slug"),
                    )
                    return _format_collection_created(result)

                elif name == "ingest_website":
                    result = await client.ingest_website(
                        start_url=arguments["start_url"],
                        collection_id=arguments["collection_id"],
                        max_pages=arguments.get("max_pages", 50),
                        url_pattern=arguments.get("url_pattern"),
                    )
                    return _format_website_ingestion(result)

                else:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]

        except Exception as e:
            logger.exception(f"Error executing tool {name}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    return server


# Formatting helpers
def _format_search_results(data: dict) -> list[TextContent]:
    """Format search results for display."""
    lines = [
        f"# Search Results for: {data['query']}",
        f"Found {data['total_results']} results (latency: {data['latency_ms']}ms)",
        "",
    ]

    for i, result in enumerate(data["results"], 1):
        lines.extend([
            f"## Result {i} (score: {result['score']:.3f})",
            f"**Document:** {result.get('document_title', 'Untitled')}",
            f"**Source:** {result.get('source_uri', 'N/A')}",
            "",
            result.get("content", "[Content not included]"),
            "",
            "---",
        ])

    if not data["results"]:
        lines.append("No results found. Try broadening your search query.")

    return [TextContent(type="text", text="\n".join(lines))]


def _format_collections(data: list) -> list[TextContent]:
    """Format collection list."""
    if not data:
        return [TextContent(type="text", text="No collections found.")]

    lines = ["# Collections", ""]
    for c in data:
        status = "active" if c.get("is_active", True) else "inactive"
        lines.append(f"- **{c['name']}** (`{c['id']}`) - {status}")
        if c.get("description"):
            lines.append(f"  {c['description']}")

    return [TextContent(type="text", text="\n".join(lines))]


def _format_collection_stats(data: dict) -> list[TextContent]:
    """Format collection statistics."""
    lines = [
        f"# Collection: {data['name']}",
        "",
        f"- **Documents:** {data['document_count']}",
        f"- **Chunks:** {data['chunk_count']}",
        f"- **Total Tokens:** {data['total_tokens']:,}",
    ]
    return [TextContent(type="text", text="\n".join(lines))]


def _format_documents(data: list) -> list[TextContent]:
    """Format document list."""
    if not data:
        return [TextContent(type="text", text="No documents found.")]

    lines = ["# Documents", ""]
    for d in data:
        lines.append(f"- **{d.get('title', 'Untitled')}** (`{d['id']}`)")
        lines.append(f"  Status: {d['status']} | Chunks: {d.get('chunk_count', 0)}")

    return [TextContent(type="text", text="\n".join(lines))]


def _format_document(data: dict) -> list[TextContent]:
    """Format single document."""
    lines = [
        f"# {data.get('title', 'Untitled Document')}",
        "",
        f"- **ID:** {data['id']}",
        f"- **Collection:** {data['collection_id']}",
        f"- **Status:** {data['status']}",
        f"- **Source:** {data.get('source_uri', 'N/A')}",
        f"- **Chunks:** {data.get('chunk_count', 0)}",
        f"- **Created:** {data['created_at']}",
    ]
    return [TextContent(type="text", text="\n".join(lines))]


def _format_chunks(data: list) -> list[TextContent]:
    """Format document chunks."""
    if not data:
        return [TextContent(type="text", text="No chunks found.")]

    lines = [f"# Document Chunks ({len(data)} chunks)", ""]
    for chunk in data:
        heading = f" - {chunk['heading']}" if chunk.get('heading') else ""
        lines.extend([
            f"## Chunk {chunk['chunk_index']}{heading}",
            chunk['content'],
            "",
        ])

    return [TextContent(type="text", text="\n".join(lines))]


def _format_ingestion_result(data: dict) -> list[TextContent]:
    """Format URL ingestion result."""
    if data.get("success"):
        doc = data["document"]
        return [TextContent(type="text", text=(
            f"Successfully ingested URL!\n\n"
            f"- **Document ID:** {doc['document_id']}\n"
            f"- **Title:** {doc['title']}\n"
            f"- **Status:** {doc['status']}\n"
            f"- **Chunks:** {doc['chunk_count']}\n"
            f"- **Tokens:** {doc['total_tokens']}"
        ))]
    else:
        return [TextContent(type="text", text=f"Ingestion failed: {data.get('error', 'Unknown error')}")]


def _format_collection_created(data: dict) -> list[TextContent]:
    """Format created collection."""
    return [TextContent(type="text", text=(
        f"Collection created!\n\n"
        f"- **ID:** {data['id']}\n"
        f"- **Name:** {data['name']}\n"
        f"- **Slug:** {data['slug']}"
    ))]


def _format_website_ingestion(data: dict) -> list[TextContent]:
    """Format website ingestion result."""
    lines = [
        "# Website Ingestion Results",
        "",
        f"- **Success:** {data['success']}",
        f"- **Pages Found:** {data['total_pages_found']}",
        f"- **Documents Processed:** {data['documents_processed']}",
        f"- **Documents Failed:** {data['documents_failed']}",
    ]

    if data.get("errors"):
        lines.extend(["", "## Errors:"])
        for error in data["errors"][:5]:  # Show first 5 errors
            lines.append(f"- {error}")

    return [TextContent(type="text", text="\n".join(lines))]


async def main():
    """Run the MCP server."""
    settings = get_settings()
    server = create_server(settings)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
