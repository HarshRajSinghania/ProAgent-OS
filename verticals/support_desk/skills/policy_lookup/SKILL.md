---
id: policy_lookup
name: Policy Lookup
description: Find the support policy or FAQ passage that answers a customer and quote it
---

# Policy Lookup

Search the tenant knowledge base before you answer. Return the best matching policy title, a short quote, and the source file. If nothing matches, say the knowledge base does not cover it. Do not paraphrase a rule that is not in the retrieved passage.

`run.py` ranks bundled fixture passages, or passages you pass in, for the offline demo. A live agent should still call `kb_search`.
