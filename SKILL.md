---
name: godaddy-ops
description: Operate GoDaddy domains and DNS through the REST API. Use for account domain inventory, expiry and auto-renew checks, DNS records, nameservers, domain settings, and GoDaddy API authentication or troubleshooting. Use the authoritative DNS provider for records hosted outside GoDaddy.
---

# GoDaddy Ops

Use the bundled Python 3.10+ standard-library client on macOS, Linux, or WSL. Resolve scripts relative to this skill directory; no third-party packages are required. The same SKILL.md works with Claude Code and Codex. This skill manages GoDaddy resources; external authoritative DNS must be managed with that provider.

## Credentials

Default: `~/.config/godaddy/credentials.json`, directory `0700`, file `0600`. Global `--credentials PATH` overrides it. Never print tokens, pass them in command arguments, or copy them into task memory. Accepted JSON:

```json
{"auth_type":"pat","token":"<personal-access-token>"}
```

```json
{"auth_type":"sso-key","key":"<classic-key>","secret":"<classic-secret>"}
```

Credentials can be created on the [GoDaddy developer portal](https://developer.godaddy.com/personal-access-token). Prefer a scoped PAT for new integrations. Obtain authorization before retrieving or exporting a secret; existing session authorization is sufficient. Never require the user to paste a token into chat.

1Password is optional. If the operator uses it, ask for the item/vault and exact PAT field, and use the desktop-integrated `op` CLI. Capture item JSON in a process and print only field labels/types/section names when disambiguation is needed. Never print the full item or its values. Import just the selected PAT:

```bash
python3 scripts/import_1password.py --item 'GoDaddy API' --vault 'Infrastructure' --field token
```

The importer refuses ambiguous fields or an existing credential file. `--replace` explicitly replaces the local file, without rotating the upstream token. `--vault` and `--section` disambiguate names. If unlock fails or is canceled, stop credential-dependent work; do not bypass it.

For permission introspection, see [API notes](references/api.md#permission-introspection). No public PAT scope-introspection endpoint was found in the official documentation checked on 2026-10-12. Successful reads establish effective read capability, not the exact granted scopes or absence of write permissions. Do not probe writes to discover permissions.

## Reads

```bash
python3 scripts/godaddy.py domains
python3 scripts/godaddy.py domains --format json
python3 scripts/godaddy.py domain example.com
python3 scripts/godaddy.py domain example.com --customer-id '<customer UUID>'
python3 scripts/godaddy.py dns example.com
python3 scripts/godaddy.py request GET /v3/domains/check-availability --query domain=example.com
```

PAT inventory uses v3 and follows every `rel=next` link. Classic credentials use v1 marker pagination. `domains --api-version v1` is an explicit compatibility option; never silently fall back on authentication/authorization failure. DNS uses v3/PAT. For classic DNS, consult the current v1 reference and use `request`. Domain detail uses v2 with a customer UUID, otherwise v1; a shopper number is not a customer UUID.

Production `api.godaddy.com` is the default. Global `--environment ote` selects `api.ote-godaddy.com` and requires separate OTE credentials. The client validates destinations and refuses redirects. `domains` prints inventory fields only; raw responses may contain contacts or transfer information and must not be copied into shared logs.

## Changes

Read the relevant official operation guide and [API notes](references/api.md) before constructing a request. Read the current resource, prepare the exact body, and explain the impact. Existing authorization for that concrete change suffices; ask only if scope, destructive impact, or cost remains unauthorized.

```bash
# Local preview: no credential access or network request.
python3 scripts/godaddy.py request PUT /v3/domains/zones/example.com/dns-records/RECORD_ID --body-file /tmp/godaddy-record.json
# Add --execute only for an authorized change.
python3 scripts/godaddy.py request PUT /v3/domains/zones/example.com/dns-records/RECORD_ID --body-file /tmp/godaddy-record.json --execute
```

Non-GET requests preview unless `--execute` is present. Preview includes the body: protect output containing contacts or transfer codes. DNS PUT fully replaces a record, including type-specific fields; preserve existing values. Nameserver PUT replaces the entire set and returns an async operation: configure destination DNS first, poll to a terminal state with a bounded deadline, and verify delegation. Registrar ownership does not imply GoDaddy hosts authoritative DNS.

For v3 nameserver PUT, supply `--idempotency-key '<UUID>'`. Generate and record one UUID per domain/change; reuse that same key only when resuming the same logical request. The OpenAPI schema requires `Idempotency-Key` even though the narrative DNS guide omits it; omitting it can return HTTP 400. Check the operation's OpenAPI definition for required headers on other writes as well.

For a nameserver preview, write a **plain JSON array**, for example `["ns1.example.net", "ns2.example.net"]`, to the body file. Do not wrap it in a `nameServers` object:

```bash
python3 scripts/godaddy.py request PUT /v3/domains/domain-names/example.com/nameservers --body-file /tmp/nameservers.json --idempotency-key '<UUID-for-this-change>'
```

This command is a local preview. Add `--execute` only for the authorized change, then follow the returned operation `Location` or `links[rel=self].href` until completion and read back the domain.


Registration, renewal, transfer, cancellation, or deletion require authorization covering the exact domains and any price/term. Review the current quote before purchase execution. Never purchase as a smoke test. Read back after changes. Writes are never automatically retried: a timeout/5xx has an uncertain outcome, so inspect state before retrying. Reads also do not auto-retry; use bounded backoff for transient errors and honor Retry-After / RateLimit-Reset / retryAfterSec on 429.

## Validation

`python3 scripts/test_godaddy.py` checks pagination, credential routing, and write guards offline. `python3 scripts/godaddy.py domains` is the live read-only smoke test. Report API/environment, complete count, status, expiry, and renewal flag. Missing fields mean unknown. Inventory success proves read access only, not write permissions.

Official starting point: <https://developer.godaddy.com/en/docs/api-users/domains>. Prefer operation-specific guides when the overview disagrees: the list guide now documents v3 inventory although the overview still lists v1.
