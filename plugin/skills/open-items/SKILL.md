---
name: open-items
description: Triage AskBase open items across all customers - promises the team made, things waiting on customers, and what's overdue - then close or follow up with the user's confirmation. Use when the user asks what's pending, overdue or promised, wants a follow-up list for the week, or says an item is done.
---

# Open items triage

Open items are created from conversations (and by the team in the portal). Closing one changes what the assistant tells that customer, so close only what the user confirms.

## 1. Overview

`list_open_items` with no filters. Report the counts line (open, overdue, due in the next 7 days, waiting on customers).

## 2. Work through it, most urgent first

1. **Overdue, we owe:** `list_open_items` with `due` = `overdue`, `owner` = `us`.
2. **Due this week, we owe:** `due` = `this_week`, `owner` = `us`.
3. **Waiting on customers:** `owner` = `customer`. Flag anything older than two weeks as a candidate for a nudge.
4. **No due date:** mention the count, and offer to list them.

For each item show: title, customer, due date, and a suggested next step (do it, nudge the customer, or close it if it's clearly stale).

## 3. Closing items

When the user says something is done or no longer needed:
1. Repeat the exact item and customer, and the new status (**done** or **cancelled**).
2. Wait for a yes, then call `update_open_item` with `contact_id`, `item_id`, the status and a short `note` on how it was resolved.
3. Confirm the result.

Never close items in bulk without listing each one first. To bring back an item closed by mistake, set its status to `open`.

## 4. Prepare follow-ups

If asked, draft short follow-up messages for the overdue items, one per customer, referencing what was promised. Use `/askbase:customer-briefing` for context on any customer first. Drafts only: the user sends them.

## Errors

"CRM tools need CRM turned on": CRM is off for this project; it's enabled in the AskBase portal.
