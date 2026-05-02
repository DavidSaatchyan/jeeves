# Suggested test questions (for QA)

Use these to validate the agent against the knowledge base above.
The expected answer for each one is directly retrievable from a single doc.

1. "How much is the Business plan?" → $49/user/month
2. "What is included in the free trial?" → 14 days of Business plan, no card
3. "Do you offer a non-profit discount?" → 30% off
4. "Where is my data stored?" → Frankfurt (AWS eu-central-1) by default
5. "How do I enable 2FA?" → Settings → Security → Two-factor authentication
6. "What's the SLA for Enterprise?" → 1 hour first-response, 24x7
7. "How long does shipping to the US take?" → 3–6 business days
8. "What is the return window?" → 30 days
9. "Can I pay by bank transfer?" → Enterprise customers, NET-30
10. "Which payment methods do you accept?" → Visa, Mastercard, Amex, SEPA
11. "I forgot my password, what do I do?" → reset link at /reset
12. "Can I switch plans mid-cycle?" → Yes, upgrades are prorated immediately
13. "When is scheduled maintenance?" → Last Saturday of month, 02:00–04:00 UTC
14. "How do I invite team members?" → Settings → Members → Invite
15. "Who do I contact for sales?" → sales@acmecloud.example

## Action-triggering tests (CRM integration required)

- "Please change my tariff to business" → should call `update_tariff`
- "What is my current subscription?" → should call `get_subscription_status`
- "I want to talk to a human" → should call `escalate_to_human`
