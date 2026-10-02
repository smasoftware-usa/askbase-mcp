---
name: kb-health
description: Health check of the user's AskBase knowledge base - per-collection document and chunk counts, failed or thin documents, and a gap check that tests likely questions against search. Use when the user asks how good or complete their knowledge base is, what's missing, or why the assistant can't answer something.
---

# AskBase knowledge-base health check

Produce a short report the user can act on. Read-only: don't add or change content unless the user asks afterwards.

## 1. Inventory

1. `list_collections` (raise `limit` if there are many).
2. For each collection: `get_collection_stats` (documents, chunks, tokens) and `list_documents` with `status` set to `failed`, then to `pending` / `processing`.

Flag:
- **Empty collections** (0 documents).
- **Failed documents**, with their error if `get_document` gives one.
- **Stuck documents**: still `pending` or `processing`.
- **Thin documents**: completed but only 1-2 chunks; often a page that failed to scrape properly. Spot-check one with `get_document_chunks`.

## 2. Gap check

For each collection with content (up to 5 collections):
1. From its name, description and a sample of document titles, write 5 questions a customer would realistically ask.
2. `search` each question restricted to that collection.
3. Mark each one **answered** (a passage clearly answers it), **partial**, or **missing**.

Keep it to about 25 searches in total. Say how many you ran.

## 3. Report

- One line per collection: documents, chunks, and issues found.
- A table of the gap-check questions with their result and the best-matching document.
- **Top 3 fixes**, most useful first, for example "re-ingest the 4 failed pages from the pricing site", "add a returns policy: 3 of 5 return questions were missing", "split the 1-chunk FAQ page".

Offer `/askbase:add-content` for the missing topics.
