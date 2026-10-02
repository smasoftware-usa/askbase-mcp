"""ASK-base API HTTP client."""

from typing import Any, Optional
from uuid import UUID

import httpx

from askbase_mcp.config import Settings


class ASKClient:
    """Async HTTP client for ASK-base API."""

    def __init__(self, settings: Settings, api_key: Optional[str] = None):
        """Initialize the client. api_key overrides settings.api_key: the
        hosted server passes each caller's own key, never a shared one."""
        self.settings = settings
        self.api_key = api_key if api_key is not None else settings.api_key
        self.base_url = f"{settings.api_base_url}/v1"
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "ASKClient":
        """Enter async context - create HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
        return self

    async def __aexit__(self, *args) -> None:
        """Exit async context - close HTTP client."""
        if self._client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> Any:
        """Make an HTTP request and return JSON response."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")

        response = await self._client.request(
            method=method,
            url=path,
            params=params,
            json=json,
        )
        response.raise_for_status()
        return response.json()

    # Search
    async def search(
        self,
        query: str,
        collection_ids: Optional[list[str]] = None,
        top_k: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
        include_content: bool = True,
    ) -> dict[str, Any]:
        """Perform semantic search over document chunks."""
        return await self._request(
            "POST",
            "/query",
            json={
                "query": query,
                "collection_ids": collection_ids,
                "top_k": top_k or self.settings.default_top_k,
                "similarity_threshold": similarity_threshold
                or self.settings.default_similarity_threshold,
                "include_content": include_content,
            },
        )

    # Collections
    async def list_collections(
        self,
        skip: int = 0,
        limit: int = 20,
        is_active: Optional[bool] = None,
    ) -> list[dict[str, Any]]:
        """List collections."""
        params = {"skip": skip, "limit": limit}
        if is_active is not None:
            params["is_active"] = is_active
        return await self._request("GET", "/collections", params=params)

    async def get_collection_stats(self, collection_id: str) -> dict[str, Any]:
        """Get collection statistics."""
        return await self._request("GET", f"/collections/{collection_id}/stats")

    async def create_collection(
        self,
        name: str,
        slug: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Create a new collection."""
        return await self._request(
            "POST",
            "/collections",
            json={
                "name": name,
                "slug": slug,
                "description": description,
                "metadata": metadata,
            },
        )

    # Documents
    async def list_documents(
        self,
        collection_id: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List documents."""
        params = {"skip": skip, "limit": limit}
        if collection_id:
            params["collection_id"] = collection_id
        if status:
            params["status"] = status
        return await self._request("GET", "/documents", params=params)

    async def get_document(self, document_id: str) -> dict[str, Any]:
        """Get document details."""
        return await self._request("GET", f"/documents/{document_id}")

    async def get_document_chunks(
        self,
        document_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get document chunks."""
        return await self._request(
            "GET",
            f"/documents/{document_id}/chunks",
            params={"skip": skip, "limit": limit},
        )

    async def create_document(
        self,
        collection_id: str,
        content: str,
        title: Optional[str] = None,
        source_type: str = "text",
        source_uri: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Create a text document."""
        return await self._request(
            "POST",
            "/documents",
            json={
                "collection_id": collection_id,
                "content": content,
                "title": title,
                "source_type": source_type,
                "source_uri": source_uri,
                "metadata": metadata,
            },
        )

    # Ingestion
    async def ingest_url(
        self,
        url: str,
        collection_id: str,
        title: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Ingest content from a URL."""
        return await self._request(
            "POST",
            "/ingestion/url",
            json={
                "url": url,
                "collection_id": collection_id,
                "title": title,
                "metadata": metadata,
            },
        )

    async def ingest_website(
        self,
        start_url: str,
        collection_id: str,
        max_pages: int = 50,
        url_pattern: Optional[str] = None,
    ) -> dict[str, Any]:
        """Crawl and ingest a website."""
        return await self._request(
            "POST",
            "/ingestion/website",
            json={
                "start_url": start_url,
                "collection_id": collection_id,
                "max_pages": max_pages,
                "url_pattern": url_pattern,
            },
        )


class ASKClientError(Exception):
    """Error from ASK-base API client."""

    pass
