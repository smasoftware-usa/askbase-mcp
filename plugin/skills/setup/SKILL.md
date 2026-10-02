---
name: setup
description: First-time setup of AskBase in Claude Code - check the API key works, pick or create a collection, add a first source and run a test search. Use when the user is getting started with AskBase, says the AskBase tools aren't working, or asks how to connect their knowledge base.
---

# AskBase setup

Get the user from "plugin installed" to "a search that returns their own content", checking each step before the next.

## 1. Check the connection

Call the AskBase `list_collections` tool.

- **Works:** say which project the key belongs to (by its collections) and go to step 2.
- **"No AskBase API key" or "rejected the API key":** the key is missing or wrong. Tell the user:
  1. In the AskBase portal, open **API Keys** and create a key. For this plugin give it the `read` and `write` scopes (`write` is needed to create collections; reading and searching work without it).
  2. Set it where Claude Code starts, for example `export ASKBASE_API_KEY="ask_live_..."` in their shell profile, then restart Claude Code.

  Stop here until they've done it. Never ask them to paste the key into the chat.

## 2. Pick a collection

- If collections exist, list them with their document counts and ask which one to use (or whether to create a new one).
- To create one, ask for a name and a one-line description, then call `create_collection`. A 403 means the key lacks the `write` scope: say so and how to fix it (step 1).

## 3. Add a first source

Ask what to start with, and use the matching tool:
- one web page → `ingest_url`
- a whole site or docs section → `ingest_website` (suggest `max_pages` 20-50 for a first run, and a `url_pattern` to stay inside the docs)
- text they paste → `create_document`

Confirm the collection and the source before calling. Report how many documents were created and any that failed.

## 4. Publish and test it

New documents start as drafts and aren't searchable until published. When processing has finished (`list_documents` shows `completed`), ask whether to publish them, then call `publish_documents`.

Ask for a question their customers would ask, or propose one from the content just added. Call `search` with it. Show the top result with its document title. If nothing relevant comes back, try one rephrasing; if still nothing, check `list_documents` for that collection: documents still `processing`, or still `draft` (not published), won't appear.

## 5. Point to what's next

Mention the other AskBase skills: `/askbase:answer` (answers with sources), `/askbase:add-content`, `/askbase:kb-health`.
