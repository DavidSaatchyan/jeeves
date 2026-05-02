# Frequently Asked Questions

## Account & login

**Q: I forgot my password.**
Go to https://app.acmecloud.example/reset, enter your email, and follow
the link we send you. The link expires in 30 minutes.

**Q: Can I change the email on my account?**
Yes. Go to *Settings → Profile → Email* and click *Change email*. You will
need to confirm the change from both the old and the new mailbox.

**Q: How do I enable two-factor authentication?**
*Settings → Security → Two-factor authentication*. We support TOTP apps
(Google Authenticator, 1Password, Authy) and hardware keys (YubiKey).

## Billing

**Q: When will I be charged?**
On the same day each month (or year) as the day you subscribed.
The first invoice is issued immediately after the free trial ends.

**Q: Can I switch plans mid-cycle?**
Yes. Upgrades are prorated and take effect immediately. Downgrades take
effect at the end of the current billing period.

**Q: Which payment methods do you accept?**
Visa, Mastercard, American Express, and SEPA direct debit for EU customers.
Enterprise customers can pay by bank transfer on NET-30 terms.

**Q: Where do I download invoices?**
*Settings → Billing → Invoices* — you can download them as PDF.

## Data & security

**Q: Where is my data stored?**
Primary region is Frankfurt, Germany (AWS eu-central-1). Enterprise
customers can request US (us-east-1) or APAC (ap-southeast-1).

**Q: Do you encrypt data at rest?**
Yes. AES-256 at rest, TLS 1.3 in transit.

**Q: Are you GDPR compliant?**
Yes. Our DPA is available at https://acmecloud.example/legal/dpa.

## Integrations

**Q: How do I connect my Slack workspace?**
*Settings → Integrations → Slack → Connect*. You will be redirected to
Slack's OAuth screen. Only workspace admins can complete the connection.

**Q: Can I export my data?**
Yes. *Settings → Data → Export* produces a ZIP with CSV/JSON dumps of
all records. Exports are available for 7 days.
