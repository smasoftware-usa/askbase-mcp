# ASKbase MCP Server

MCP (Model Context Protocol) server for [ASK-base](https://askbase.com) RAG API. Enables AI assistants like Claude Desktop, Cursor, and Claude Code to search and manage your knowledge base.

## Features

- **Semantic Search** - Query your knowledge base using natural language
- **Collection Management** - List, create, and inspect document collections
- **Document Management** - View documents and their chunks
- **Content Ingestion** - Add URLs and websites to your knowledge base

## Installation

### Using uvx (recommended)

```bash
uvx askbase-mcp
```

### Using pip

```bash
pip install askbase-mcp
```

## Configuration

Set your ASK-base API key as an environment variable:

```bash
export ASK_API_KEY="ask_live_your_api_key_here"
```

### Optional Configuration

```bash
# API base URL (default: https://api.askbase.com)
export ASK_API_BASE_URL="https://api.askbase.com"

# Default collection for searches
export ASK_DEFAULT_COLLECTION_ID="your-collection-uuid"

# Default number of results (default: 5)
export ASK_DEFAULT_TOP_K=10

# Default similarity threshold (default: 0.7)
export ASK_DEFAULT_SIMILARITY_THRESHOLD=0.75
```

## Usage with AI Assistants

### Claude Desktop

Add to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "askbase": {
      "command": "uvx",
      "args": ["askbase-mcp"],
      "env": {
        "ASK_API_KEY": "ask_live_your_api_key_here"
      }
    }
  }
}
```

### Cursor

Add to your Cursor MCP configuration (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "askbase": {
      "command": "uvx",
      "args": ["askbase-mcp"],
      "env": {
        "ASK_API_KEY": "ask_live_your_api_key_here"
      }
    }
  }
}
```

### Claude Code CLI

```bash
claude mcp add askbase -- uvx askbase-mcp
```

## Available Tools

| Tool | Description |
|------|-------------|
| `search` | Semantic search over your knowledge base |
| `list_collections` | List all document collections |
| `get_collection_stats` | Get collection statistics (docs, chunks, tokens) |
| `list_documents` | List documents in a collection |
| `get_document` | Get document details |
| `get_document_chunks` | Get document text chunks |
| `ingest_url` | Scrape and ingest a URL |
| `create_document` | Create a text document |
| `create_collection` | Create a new collection |
| `ingest_website` | Crawl and ingest a website |

## Example Interactions

Once configured, you can ask your AI assistant:

- "Search my knowledge base for return policies"
- "List all my document collections"
- "Show me the stats for the support-docs collection"
- "Add this URL to my FAQ collection: https://example.com/help"
- "What documents are in the product-info collection?"

## Development

```bash
# Clone the repository
git clone https://github.com/smasoftware-usa/askbase-mcp.git
cd askbase-mcp

# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

## Getting an API Key

1. Sign up at [ASK-base](https://askbase.com)
2. Navigate to your dashboard
3. Create an API key (format: `ask_live_xxx`)

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

- [GitHub Issues](https://github.com/smasoftware-usa/askbase-mcp/issues)
- [ASK-base Documentation](https://docs.askbase.com)
