# GoDaddy API notes

Verified against official documentation on 2026-10-12. Recheck the specific operation before a write; these are navigation notes, not copied schemas.

| Task | API / behavior |
| --- | --- |
| Inventory | `GET /v3/domains/domain-names`; PAT; `{items, links}`; follow `rel=next` until absent. Fields include domain, status, expiresAt, autoRenew. No lifecycle filter by default. |
| Legacy inventory | `GET /v1/domains?limit=100`; array; next marker is the last domain name; stop when fewer than limit. Fields use expires and renewAuto. |
| Detail | Prefer `GET /v2/customers/{customerId}/domains/{domain}` when customer UUID is known; account-scoped v1 detail remains available. |
| DNS list/add | `GET` / `POST /v3/domains/zones/{zone}/dns-records`; GET paginates; POST creates one record and returns 201 plus Location. |
| DNS replace/delete | `PUT` / `DELETE /v3/domains/zones/{zone}/dns-records/{recordId}`; PUT replaces all writable fields. GoDaddy-managed NS/SOA cannot be edited. |
| Nameservers | `PUT /v3/domains/domain-names/{domain-name}/nameservers`; body is 2–13 hostname strings; 202 async, poll the returned operation. |
| Renewal/settings | v1; inspect current renewal guide for PATCH settings versus paid POST renewal. |
| Registration | v3 quote/execute plus async polling; inspect current guide and quote before any paid action. |

PAT uses `Authorization: Bearer …`; classic key/secret uses `Authorization: sso-key …:…`, supports v1/v2, and does not work with v3. Never reinterpret a PAT as a classic key or use a token from another provider.

Nameserver PUT requires `Idempotency-Key` (16–64 characters; UUID recommended), as declared in [v3 OpenAPI](https://developer.godaddy.com/openapi/domains-v3.json). The guide examples omit it. An unkeyed request can fail with HTTP 400. Use the bundled `--idempotency-key` option and retain the key in change evidence. Prefer the formal operation schema over incomplete narrative examples.

Read scope: `domains.domain:read`. Writes have distinct scopes, including `domains.dns:update`, `domains.nameserver:update`, and domain/contact/transfer-specific scopes. A 403 is not proof of invalid credentials: distinguish missing scopes, account eligibility, and resource ownership by API code. Management access requires at least one domain or a qualifying plan, according to the current auth guide; do not repeat obsolete historical domain-count thresholds.

DNS TTL is 600–86400 seconds. MX/SRV/CAA require their type-specific fields. GET the current record before replacing it. External DNS is managed at the authoritative DNS provider, even if GoDaddy is registrar.

429 may have an empty body. Honor Retry-After, RateLimit-Reset, or retryAfterSec; do not assume a fixed global rate. The client reports a failure without retrying, and never follows HTTP redirects with credentials. Generic requests return HTTP status and Location so async acceptance is not mistaken for completion.

## Permission introspection

On 2026-10-12, the official authentication guide, PAT setup guide, complete `llms-full.txt` documentation, REST index, and Domains v1/v2 OpenAPI definitions did not document a public PAT introspection endpoint that returns granted scopes. This is a documentation finding, not proof that no internal endpoint exists. Do not invent endpoints or send tokens to third-party token decoders.

Do not assume a PAT is a JWT or that local decoding reveals its granted scopes. GoDaddy's [PAT management page](https://developer.godaddy.com/personal-access-token) is the account UI to inspect token configuration; sign-in may be required. Check scope metadata there, or consult the creation record/provider support if the UI omits it. Do not recreate or broaden a token merely to inspect it.

A successful domain inventory establishes effective read capability, not a complete scope enumeration. A write scope may also satisfy reads. Similarly, an authorized nameserver update demonstrates that operation's capability for the target domain, not permission for DNS record edits, purchases, renewals, or transfers. Never mutate resources merely to discover token permissions.

## Official sources

- [Overview](https://developer.godaddy.com/en/docs/api-users/domains)
- [Authentication and scopes](https://developer.godaddy.com/en/docs/api-users/auth)
- [Domain inventory](https://developer.godaddy.com/en/docs/api-users/domains/manage/list)
- [DNS and nameservers](https://developer.godaddy.com/en/docs/api-users/domains/manage/dns)
- [Renewals](https://developer.godaddy.com/en/docs/api-users/domains/manage/renewals)
- [Registration](https://developer.godaddy.com/en/docs/api-users/domains/register)
- [Errors](https://developer.godaddy.com/en/docs/api-users/errors)
- [Rate limits](https://developer.godaddy.com/en/docs/api-users/rate-limits)
- [v1 pagination](https://developer.godaddy.com/en/docs/api-users/pagination)
- [v3 API reference](https://developer.godaddy.com/en/docs/references/rest/domains/v3)

Markdown versions are available at `https://developer.godaddy.com/llms.mdx/api-users/<guide-path>`. The overview and operation guides currently disagree about some version availability; use the operation guide and actual API response.
