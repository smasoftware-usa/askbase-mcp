# AskBase MCP server and Claude Code plugin

Connect AI assistants to your [AskBase](https://askbase.co) project: search and grow your knowledge base, see what customers asked that your assistant couldn't answer, brief yourself on a customer, and test your assistant's answers.

This repository contains:

- **The AskBase plugin for Claude Code** (`plugin/`): the MCP server connection plus skills for common tasks.
- **The AskBase MCP server** (`src/askbase_mcp/`): hosted by AskBase, or run locally.

## Claude Code plugin (recommended)

```
/plugin marketplace add smasoftware-usa/askbase-mcp
/plugin install askbase@askbase
```

Create an API key in the AskBase portal (**API Keys**, with the `read` and `write` scopes) and set it before starting Claude Code:

```bash
export ASKBASE_API_KEY="ask_live_..."
```

Then run `/askbase:setup`. See [plugin/README.md](plugin/README.md) for the skills.

## Hosted MCP server (other clients)

Any MCP client that supports streamable HTTP can connect directly:

- **URL:** `https://mcp.askbase.co/mcp`
- **Header:** `X-API-Key: <your AskBase API key>` (or `Authorization: Bearer <key>`)

Claude Code without the plugin:

```bash
claude mcp add --transport http askbase https://mcp.askbase.co/mcp \
  --header "X-API-Key: $ASKBASE_API_KEY"
```

Cursor (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "askbase": {
      "url": "https://mcp.askbase.co/mcp",
      "headers": { "X-API-Key": "ask_live_your_key_here" }
    }
  }
}
```

The server is stateless: every request uses only the API key it carries. It stores no keys and keeps no sessions.

## Local server (stdio)

Run the server on your own machine (Python 3.10+, [uv](https://docs.astral.sh/uv/)):

```json
{
  "mcpServers": {
    "askbase": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/smasoftware-usa/askbase-mcp", "askbase-mcp"],
      "env": { "ASK_API_KEY": "ask_live_your_key_here" }
    }
  }
}
```

Optional settings (environment variables):

| Variable | Default | Meaning |
|---|---|---|
| `ASK_API_BASE_URL` | `https://api.askbase.co` | AskBase API |
| `ASK_DEFAULT_TOP_K` | `5` | Search results per query |
| `ASK_DEFAULT_SIMILARITY_THRESHOLD` | `0.2` | Minimum similarity for search results |

## Tools

| Area | Tools |
|---|---|
| Knowledge base | `search`, `list_knowledge_bases`, `list_collections`, `get_collection_stats`, `list_documents`, `get_document`, `get_document_chunks`, `ingest_url`, `ingest_website`, `create_document`, `publish_documents`, `create_collection` |
| Insights | `list_unanswered_questions`, `get_unanswered_question`, `suggest_answer`, `list_failed_lookups` |
| CRM | `find_contacts`, `get_contact`, `get_contact_memory`, `list_open_items`, `update_open_item`, `find_companies`, `get_company` |
| Deals | `list_deals`, `get_deal`, `deal_pipeline_summary`, `list_deal_suggestions`, `create_deal`, `move_deal`, `decide_deal_suggestion` |
| Assistant | `ask_assistant` |

New documents start as **drafts** and aren't searchable or used by your assistant until published (`publish_documents`). CRM tools need CRM turned on for the project. `ask_assistant` runs your live assistant, so it uses your model's tokens.

## API key scopes

| Scope | Needed for |
|---|---|
| any valid key | search; reading collections, documents, insights and CRM; ingesting pages and text |
| `write` | creating collections, publishing documents |

## Development

```bash
git clone https://github.com/smasoftware-usa/askbase-mcp.git
cd askbase-mcp
uv venv && uv pip install -e ".[dev]"
.venv/bin/pytest
```

- `src/askbase_mcp/tools.py`: every tool, shared by both transports.
- `src/askbase_mcp/http_server.py`: the hosted server (`uvicorn askbase_mcp.http_server:app`).
- `src/askbase_mcp/server.py`: the local stdio server (`askbase-mcp`).
- `plugin/`: the Claude Code plugin; `.claude-plugin/marketplace.json` lists it. Validate with `claude plugin validate ./plugin`.

## Security

Please report vulnerabilities privately through GitHub's **Security → Report a vulnerability** on this repository, not in a public issue. Your API key is sent only to the AskBase MCP server and API, and is used only for your own requests.

## License

MIT. See [LICENSE](LICENSE).
