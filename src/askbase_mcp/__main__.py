"""Entry point for running ASKbase MCP server."""

import asyncio
from askbase_mcp.server import main

if __name__ == "__main__":
    asyncio.run(main())
