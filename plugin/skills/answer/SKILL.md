---
name: answer
description: Answer a question from the user's AskBase knowledge base, citing the documents used, and say clearly when the knowledge base doesn't cover it. Use when the user asks something their company docs, policies, product or support content should answer, or says "check AskBase", "what do our docs say", or "according to the knowledge base".
---

# Answer from the AskBase knowledge base

The answer must come from the knowledge base, not from general knowledge. A short, cited answer beats a long one.

## Steps

1. **Search.** Call the AskBase `search` tool with the question in plain words. If the user named a collection or product area, find its ID with `list_collections` and pass it in `collection_ids`.
2. **Judge the results.** Keep only passages that actually answer the question. Scores help but aren't proof: read the text.
3. **If nothing answers it**, search once more with different words: synonyms, the product's own terms from any partial hits, or the other language the content may be in. Don't search more than twice in total.
4. **Answer:**
   - Lead with the direct answer in one or two sentences.
   - Use only what the passages say. Don't fill gaps from general knowledge; if a detail is missing, say it's not in the knowledge base.
   - Cite each fact with its document title, e.g. *(Refund policy › Exceptions)*. Add the source URL when the result has one.
   - If passages disagree, show both with their titles and say they conflict.
5. **If the knowledge base doesn't cover it**, say so plainly (search only sees published documents, so a draft on the topic won't show up) ("The knowledge base doesn't cover X."), mention the closest thing it does cover, and offer to add the missing content with `/askbase:add-content`.

## When a passage is cut off

If the answer seems to continue beyond a passage, call `get_document_chunks` for that document and read the neighbouring chunks before answering.
