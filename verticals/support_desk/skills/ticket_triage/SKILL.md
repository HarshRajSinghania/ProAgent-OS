---
id: ticket_triage
name: Ticket Triage
description: Classify a support ticket against policy passages and cite the lines used
---

# Ticket Triage

Use this skill when a new customer ticket arrives.

1. Read the subject and body. Do not answer from memory.
2. Search the private knowledge base for the policy or FAQ that governs the request.
3. Assign one category: billing, access, outage, or general.
4. Assign one priority: urgent (service down, lockout, or account takeover), high (billing or refund), or normal.
5. Reply with the priority, the category, one next step, and a citation (policy title plus a short quote).
6. If no passage matches, say so and emit a follow-up for a human. Do not invent refund windows, response times, or exceptions.

`run.py` is a deterministic keyword triage for the offline demo. It is not a production classifier. Pass `passages` from `kb_search` when you have them; otherwise it reads `verticals/support_desk/fixtures/`.
