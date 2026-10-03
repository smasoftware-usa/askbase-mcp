---
name: customer-briefing
description: One-page briefing on a customer or company before a call or reply - who they are, their company, open deals, what the AskBase assistant remembers about them, what we promised them and what they've talked about recently. Use when the user asks about a specific customer, contact or company, e.g. "brief me on Ana Ruiz", "what do we know about acme.com", or "I'm calling John in 10 minutes".
---

# Customer briefing

Everything here comes from the AskBase CRM and the assistant's memory of this customer. It's personal data: show it to the user, don't copy it anywhere else.

## 1. Find the contact (or company)

`find_contacts` with the name, email or company the user gave. If the user named a company or a domain rather than a person, use `find_companies` and `get_company` instead: brief on the company (profile, its people, open deals, pending suggestions) and offer to brief on one of its contacts.
- **One match:** use it.
- **Several:** list them (name, email, company, last seen) and ask which one.
- **None:** say so and suggest another spelling or their email.
- **"CRM tools need CRM turned on":** CRM is off for this project; it's enabled in the AskBase portal under CRM settings. Stop there.

## 2. Gather

- `get_contact` for the profile. If it shows a company ID, `get_company` for the company and its open deals.
- `list_deals` with `contact_id` for the deals this person is on (open ones; mention recent won/lost only if asked).
- `list_deal_suggestions` with `contact_id` for buying or leaving signals the assistant noticed that nobody has decided on yet.
- `get_contact_memory` for current facts and preferences, open items, recent conversation summaries and activity.

## 3. Write the briefing

Keep it to one screen, in this order:

1. **Who:** name, company and role, stage, language and time zone, customer since, last seen, number of conversations.
2. **Deals:** each open deal with value, stage, close date and their role on it; flag any deal **at risk** (with the customer's words) or past its close date. Then pending suggestions, quoting the customer's words.
3. **Open promises:** what *we* owe them first (with due dates, overdue in bold), then what we're waiting on from them.
4. **Know before you talk:** preferences, constraints and "do not repeat" items, in plain words.
5. **Recently:** two to four bullets from the latest conversation summaries, newest first.
6. **Suggested opener:** one sentence that picks up where things left off (e.g. the overdue promise, or the quote they asked for).

Say plainly when a section is empty rather than guessing. Don't speculate beyond what the data says.

## 4. Follow-ups

Offer to close finished promises (`/askbase:open-items`), review deals and suggestions (`/askbase:pipeline-review`), or look up anything they asked about in the knowledge base (`/askbase:answer`).
