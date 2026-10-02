---
name: add-content
description: Add content to the user's AskBase knowledge base - a web page, a whole website or docs section, or pasted text - into the right collection, then confirm it is searchable. Use when the user wants AskBase to know about something new, to ingest a URL or site, or to fill a gap the knowledge base couldn't answer.
---

# Add content to AskBase

Adding content changes what the user's customers will be told, so confirm the destination and the source before writing.

## 1. Work out what and where

- **What:** one page (URL), a site or section (start URL), or text the user pasted or that you drafted together.
- **Where:** call `list_collections`. If the user didn't say which collection, propose the best fit by name and description and ask. Create a new collection with `create_collection` only if they want one.
- **Duplicates:** for a single page or text, `search` for its main topic first. If very similar content already exists, show it and ask whether to add anyway or skip.

## 2. Confirm, then add

State the plan in one line, e.g. *"Add https://example.com/pricing to **Website** (one page)."* and wait for a yes. Then:

| Content | Tool | Notes |
|---|---|---|
| One web page | `ingest_url` | Public http(s) pages only; private or internal addresses are refused. |
| A site or section | `ingest_website` | Set `max_pages` (default 50) and a `url_pattern` such as `^https://example.com/docs/` to stay in scope. Unchanged pages are skipped on re-runs. |
| Text | `create_document` | Give it a clear title; it becomes the citation users see. Use markdown headings for long text. Set `source_uri` if it came from somewhere. |

## 3. Check it worked

- Report what was created (titles, document count) and anything that failed, with the reason.
- Documents are processed after upload. If `get_document` shows `pending` or `processing`, say it will be searchable shortly.
- When processing is done, `search` for a question the new content answers and show that it comes back.

## Errors

- **403:** the API key lacks the `write` scope (only needed for creating collections) or the action isn't allowed. Explain and point to `/askbase:setup`.
- **"private or reserved address":** the URL isn't publicly reachable. Ask for a public URL or the text itself.
