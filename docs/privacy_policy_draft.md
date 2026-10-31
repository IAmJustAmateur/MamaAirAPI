# Privacy policy working draft

Public route: `/privacy-policy` (no trailing slash), template:
`templates/legal/privacy_policy.html`. The existing `/delete-account` page is
linked by its Django URL name. No migrations, new dependencies or consent-flow
changes are required. Existing Caddy forwarding covers the route.

The English page is explicitly a draft and sends `X-Robots-Tag: noindex, nofollow`
and `Cache-Control: no-store`. Do not submit it as a completed store policy.
Update the visible revision date whenever the wording changes.

Before finalisation, confirm operator identity and contact, target countries and
age limits, hosting and backups, the complete mobile SDK/provider inventory,
retention and deletion practices, applicable rights and legal bases, and any
research or secondary use. These unconfirmed details are omitted from the page.
Review actual mobile collection and permission disclosures alongside the policy.

Validation:

```powershell
python manage.py test api.tests.test_privacy_pages
python scripts/test_privacy_browser.py
```

The browser test uses a temporary database and local server, checks anonymous
access at mobile and desktop widths, verifies the draft label and page reload,
and follows the deletion link without deleting any account. Screenshots are saved
under `.e2e-artifacts/privacy/`. CI runs it with the existing Chromium dependency.
