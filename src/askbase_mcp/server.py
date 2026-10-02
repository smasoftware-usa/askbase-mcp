"""Local (stdio) MCP server: for Claude Desktop, Cursor or Claude Code
running the server on your own machine. Uses the ASK_API_KEY environment
variable. The tools are shared with the hosted server (tools.py)."""

import asyncio

from askbase_mcp.config import get_settings
from askbase_mcp.tools import build_server


async def run() -> None:
    server = build_server(get_settings(), allow_env_key=True)
    await server.run_stdio_async()


def main() -> None:
    """Console-script entry point (`askbase-mcp`)."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
