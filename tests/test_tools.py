"""Tests for MCP tools with mocked HTTP responses."""

import os
import pytest
import respx
from httpx import Response
from unittest.mock import patch

# Set test API key before importing
os.environ["ASK_API_KEY"] = "ask_live_test123456789012345678901234"
os.environ["ASK_API_BASE_URL"] = "https://api.test.com"


@pytest.fixture
def mock_api():
    """Create a mocked API context."""
    with respx.mock(base_url="https://api.test.com/v1") as respx_mock:
        yield respx_mock


@pytest.mark.asyncio
async def test_search_tool(mock_api):
    """Test the search tool."""
    from askbase_mcp.client import ASKClient
    from askbase_mcp.config import get_settings

    # Mock the search endpoint
    mock_api.post("/query").mock(return_value=Response(200, json={
        "query": "test query",
        "results": [
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "collection_id": "col-1",
                "content": "This is the test content",
                "score": 0.95,
                "document_title": "Test Document",
                "source_uri": "https://example.com",
                "heading": "Section 1",
                "chunk_index": 0,
                "metadata": {}
            }
        ],
        "total_results": 1,
        "search_type": "similarity",
        "latency_ms": 50
    }))

    settings = get_settings()
    async with ASKClient(settings) as client:
        result = await client.search(query="test query")

    assert result["total_results"] == 1
    assert result["results"][0]["score"] == 0.95
    assert result["results"][0]["content"] == "This is the test content"


@pytest.mark.asyncio
async def test_list_collections_tool(mock_api):
    """Test the list_collections tool."""
    from askbase_mcp.client import ASKClient
    from askbase_mcp.config import get_settings

    mock_api.get("/collections").mock(return_value=Response(200, json=[
        {
            "id": "col-1",
            "name": "Test Collection",
            "slug": "test-collection",
            "description": "A test collection",
            "is_active": True,
            "metadata": {},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
        }
    ]))

    settings = get_settings()
    async with ASKClient(settings) as client:
        result = await client.list_collections()

    assert len(result) == 1
    assert result[0]["name"] == "Test Collection"


@pytest.mark.asyncio
async def test_get_collection_stats_tool(mock_api):
    """Test the get_collection_stats tool."""
    from askbase_mcp.client import ASKClient
    from askbase_mcp.config import get_settings

    mock_api.get("/collections/col-1/stats").mock(return_value=Response(200, json={
        "id": "col-1",
        "name": "Test Collection",
        "document_count": 10,
        "chunk_count": 50,
        "total_tokens": 25000
    }))

    settings = get_settings()
    async with ASKClient(settings) as client:
        result = await client.get_collection_stats("col-1")

    assert result["document_count"] == 10
    assert result["chunk_count"] == 50
    assert result["total_tokens"] == 25000


@pytest.mark.asyncio
async def test_ingest_url_tool(mock_api):
    """Test the ingest_url tool."""
    from askbase_mcp.client import ASKClient
    from askbase_mcp.config import get_settings

    mock_api.post("/ingestion/url").mock(return_value=Response(200, json={
        "success": True,
        "document": {
            "document_id": "doc-1",
            "title": "Ingested Page",
            "status": "completed",
            "chunk_count": 5,
            "total_tokens": 1200
        },
        "error": None
    }))

    settings = get_settings()
    async with ASKClient(settings) as client:
        result = await client.ingest_url(
            url="https://example.com/page",
            collection_id="col-1"
        )

    assert result["success"] is True
    assert result["document"]["chunk_count"] == 5


@pytest.mark.asyncio
async def test_create_document_tool(mock_api):
    """Test the create_document tool."""
    from askbase_mcp.client import ASKClient
    from askbase_mcp.config import get_settings

    mock_api.post("/documents").mock(return_value=Response(201, json={
        "id": "doc-1",
        "collection_id": "col-1",
        "title": "New Document",
        "status": "pending",
        "chunk_count": 0,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
    }))

    settings = get_settings()
    async with ASKClient(settings) as client:
        result = await client.create_document(
            collection_id="col-1",
            content="This is the document content",
            title="New Document"
        )

    assert result["title"] == "New Document"
    assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_api_error_handling(mock_api):
    """Test that API errors are handled properly."""
    from askbase_mcp.client import ASKClient
    from askbase_mcp.config import get_settings
    import httpx

    mock_api.get("/collections").mock(return_value=Response(401, json={
        "detail": "Invalid API key"
    }))

    settings = get_settings()
    async with ASKClient(settings) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.list_collections()
