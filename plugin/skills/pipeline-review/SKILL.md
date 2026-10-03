---
name: pipeline-review
description: Review the AskBase sales pipeline - open value and weighted forecast, deals past their close date, stalled and at-risk deals, and deal suggestions the assistant noticed in customer conversations - then move deals or decide suggestions with the user's confirmation. Use when the user asks how the pipeline or forecast looks, what deals need attention, what's at risk, or to go through suggested deals.
---

# Pipeline review

Deals live in the AskBase CRM. The assistant suggests deals from what customers say, but only a person decides: never move a deal or accept a suggestion without the user's yes.

Amounts are per currency and never converted. Report each currency separately; don't add USD to EUR.

## 1. Overview

`deal_pipeline_summary` (default 90 days). Report in a few lines:
- Pipelines and their stages (only if there's more than one pipeline, or the user asks).
- Open value by stage, and the weighted forecast for the next three close months.
- Win rate, won value and average time to win over the period.
- How many deals are past their close date.

## 2. What needs attention, most urgent first

1. **At risk:** `list_deals` (status `open`) and pick the ones marked **at risk**; quote the customer's words from `get_deal`.
2. **Past close date:** the overdue list from the summary. For each: value, stage, how late, main contact.
3. **Stalled:** open deals sorted by `updated` whose last change is more than 30 days ago (check with `get_deal` history when unsure).
4. **Pending suggestions:** `list_deal_suggestions`. For each, show what is suggested (new deal, move forward, at risk), the contact, and the customer's own words.

For each item suggest one next step: update the close date, move the stage, mark won or lost, contact the customer, or (for suggestions) accept or dismiss. Use `/askbase:customer-briefing` for context on a customer before suggesting what to say.

## 3. Making changes (only after a yes)

Repeat exactly what will change, wait for a yes, then:
- **Move a deal:** `move_deal` with the stage name. Moving to a lost stage: ask for the reason first and pass `lost_reason`.
- **Accept a suggestion:** `decide_deal_suggestion` with `accept`. For a new deal, first confirm the name, amount and currency, and a close date if the user knows one, and pass them. Advance moves the deal to the suggested stage; at risk flags the deal.
- **Dismiss a suggestion:** `decide_deal_suggestion` with `dismiss`.
- **Create a deal the user describes:** `create_deal`, with a contact or company when known.

Change one thing per confirmation. Never accept or dismiss suggestions in bulk without listing each one first. Report the result of each change.

## Errors

- "CRM tools need CRM turned on": CRM is off for this project; it's enabled in the AskBase portal.
- A refusal mentioning the "write" scope: the API key can read but not change deals; the user needs a key with the write scope.
