---
name: fill-gaps
description: Find what customers asked the AskBase assistant that it couldn't answer, rank the gaps, and draft the missing content (or flag the integration fix) for the user to approve. Use when the user asks what's missing from their knowledge base, what customers can't get answers to, or how to improve the assistant.
---

# Fill AskBase knowledge gaps

Turn real unanswered questions into content. Nothing is added without the user's approval.

## 1. Collect the gaps

1. `list_unanswered_questions` (status `open`). These are groups of real customer questions with no good answer.
2. `list_failed_lookups` (status `open`). These are tool lookups that came back empty (order not found, account unknown...). They usually point to data or integration problems, not missing documents.

If both are empty, say so: either the assistant is answering well or there isn't enough traffic yet. Offer `/askbase:kb-health` for a proactive gap check instead.

## 2. Rank

Order the groups by how often they're asked, then how recent. Take the top 5. For each, call `get_unanswered_question` to read the actual customer wording.

## 3. Check it's really missing

For each group, `search` the knowledge base with two or three of the real questions. Classify:
- **Missing:** nothing relevant. Needs new content.
- **Hard to find:** the answer exists but scores low or uses different words. Needs better wording or headings in that document, not a new one.
- **Not a content problem:** needs live data or an action (e.g. "where is my order"). Call `suggest_answer` for AskBase's recommendation (new tool, flow or data fix) and report it; content won't fix it.

## 4. Draft

For each **missing** topic, draft a short document: a clear title phrased the way customers ask, the answer in the first paragraph, details after. Never invent facts (prices, dates, policies). Where you don't know, leave a visible `[TODO: confirm …]` and list it for the user.

## 5. Review with the user

Show a table: topic, times asked, classification, proposed action. Then show each draft. Add only the ones the user approves, using `/askbase:add-content` (pasted text → `create_document`), in the collection they choose. They start as drafts: publish with `publish_documents` once the user has resolved the TODOs.

Close by listing the **not a content problem** items with AskBase's recommendations, for their team to handle.
