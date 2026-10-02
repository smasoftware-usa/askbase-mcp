# AskBase plugin for Claude Code

Search, grow and check your [AskBase](https://askbase.co) knowledge base from Claude Code. The plugin connects to the hosted AskBase MCP server with your own API key and adds skills for common tasks.

## Install

```
/plugin marketplace add smasoftware-usa/askbase-mcp
/plugin install askbase@askbase
```

Then give Claude Code your AskBase API key. Create one in the AskBase portal under **API Keys** with the `read` and `write` scopes, and set it before starting Claude Code:

```bash
export ASKBASE_API_KEY="ask_live_..."
```

Run `/askbase:setup` to check the connection and add your first content.

## Skills

| Skill | What it does |
|---|---|
| `/askbase:setup` | Checks the key, picks or creates a collection, adds a first source, runs a test search. |
| `/askbase:answer` | Answers from your knowledge base with cited documents, and says when it isn't covered. |
| `/askbase:add-content` | Adds a web page, a website section or text to the right collection, then checks it's searchable. |
| `/askbase:kb-health` | Reports empty collections, failed or thin documents, and gaps found by test questions. |
| `/askbase:fill-gaps` | Turns questions customers asked that the assistant couldn't answer into drafted content for you to approve. |
| `/askbase:customer-briefing` | One-page briefing on a customer: profile, what the assistant remembers, open promises, recent conversations. |
| `/askbase:open-items` | What you promised customers and what's overdue, across all contacts; closes items you confirm. |
| `/askbase:test-assistant` | Runs a question set through the live assistant, grades answers against the knowledge base, reports problems. |

New documents start as **drafts**: they aren't searchable or used by your assistant until published. The skills show you what will go live and publish only after you confirm.

Claude also uses these skills on its own when your request matches, e.g. "what do our docs say about refunds?".

## API key scopes

| Scope | Needed for |
|---|---|
| any valid key | search, listing collections and documents, ingesting pages and text |
| `write` | creating collections |

Customer briefings and open items need **CRM turned on** for the project (portal → CRM settings). `test-assistant` runs the real assistant, so each question uses your model's tokens.

Your key is sent only to the AskBase MCP server, as the `X-API-Key` header, and is used only for your own requests.

## Tools

The MCP server provides:
- **Knowledge base:** `search`, `list_knowledge_bases`, `list_collections`, `get_collection_stats`, `list_documents`, `get_document`, `get_document_chunks`, `ingest_url`, `ingest_website`, `create_document`, `publish_documents`, `create_collection`
- **Insights:** `list_unanswered_questions`, `get_unanswered_question`, `suggest_answer`, `list_failed_lookups`
- **CRM:** `find_contacts`, `get_contact`, `get_contact_memory`, `list_open_items`, `update_open_item`
- **Assistant:** `ask_assistant`
