---
name: customer-briefing
description: One-page briefing on a customer before a call or reply - who they are, what the AskBase assistant remembers about them, what we promised them and what they've talked about recently. Use when the user asks about a specific customer or contact, e.g. "brief me on Ana Ruiz", "what do we know about acme.com", or "I'm calling John in 10 minutes".
---

# Customer briefing

Everything here comes from the AskBase CRM and the assistant's memory of this customer. It's personal data: show it to the user, don't copy it anywhere else.

## 1. Find the contact

`find_contacts` with the name, email or company the user gave.
- **One match:** use it.
- **Several:** list them (name, email, company, last seen) and ask which one.
- **None:** say so and suggest another spelling or their email.
- **"CRM tools need CRM turned on":** CRM is off for this project; it's enabled in the AskBase portal under CRM settings. Stop there.

## 2. Gather

- `get_contact` for the profile.
- `get_contact_memory` for current facts and preferences, open items, recent conversation summaries and activity.

## 3. Write the briefing

Keep it to one screen, in this order:

1. **Who:** name, company and role, stage, language and time zone, customer since, last seen, number of conversations.
2. **Open promises:** what *we* owe them first (with due dates, overdue in bold), then what we're waiting on from them.
3. **Know before you talk:** preferences, constraints and "do not repeat" items, in plain words.
4. **Recently:** two to four bullets from the latest conversation summaries, newest first.
5. **Suggested opener:** one sentence that picks up where things left off (e.g. the overdue promise).

Say plainly when a section is empty rather than guessing. Don't speculate beyond what the data says.

## 4. Follow-ups

Offer to close finished promises (`/askbase:open-items`) or to look up anything they asked about in the knowledge base (`/askbase:answer`).
