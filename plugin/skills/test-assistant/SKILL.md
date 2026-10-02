---
name: test-assistant
description: Test the live AskBase assistant with a set of realistic customer questions, grade each answer against the knowledge base, and report wrong, missing or unsupported answers. Use when the user wants to check answer quality, test before launch, or verify that new content fixed a gap.
---

# Test the AskBase assistant

Each question runs the real assistant, which uses the project's model and costs tokens. The runs appear in the portal as test conversations, anonymous, so no CRM contact or memory is created.

## 1. Agree on the question set

- If the user gave questions, use them.
- If they ran this before in this conversation, offer to reuse that set to compare results.
- Otherwise draft 10 from the knowledge base: `list_collections`, then sample document titles with `list_documents`, and write the questions customers would really ask. Mix easy, specific (prices, steps, limits), and two the knowledge base should **not** answer (to check the assistant says so instead of inventing).

Show the set and the cost before running: *"10 questions = 10 assistant calls on your model."* Keep a run to 20 questions at most. Wait for a yes.

## 2. Run

For each question:
1. `ask_assistant` with the question.
2. `search` the knowledge base with the same question to see what it actually contains.

## 3. Grade each answer

- **Correct:** matches the knowledge base and uses it as a source.
- **Wrong:** contradicts the knowledge base.
- **Unsupported:** states specifics the knowledge base doesn't contain (likely invented).
- **Missed:** the knowledge base has the answer but the assistant said it didn't know.
- **Correctly declined:** an out-of-scope question the assistant rightly didn't answer.

Quote the specific sentence when marking wrong or unsupported.

## 4. Report

- Score line, e.g. *8/10 correct or correctly declined.*
- Table: question, grade, short reason, source used.
- Fixes, grouped:
  - **Missed** answers: the content exists but isn't found. Suggest clearer titles or headings.
  - **Wrong** or **unsupported** answers: suggest the content to add or correct, via `/askbase:add-content` or `/askbase:fill-gaps`.

Keep the question set in the conversation so the user can rerun it after fixing things.
