# GoDaddy Ops

Manage GoDaddy domains and DNS with an agent skill for Claude Code and Codex.

## How to use this skill

Ask your agent in natural language:

- "List my GoDaddy domains, expiration dates, and auto-renew settings."
- "Show the DNS records for example.com."
- "Prepare a nameserver change for example.com; show the request before executing it."
- "Help diagnose a GoDaddy API 403 without changing any resources."

The skill reads complete paginated inventories, inspects domain and DNS state, prepares JSON API requests, and executes changes within your authorization. Writes preview locally unless `--execute` is supplied. It verifies nameserver changes through the returned operation and registrar state.

## Requirements and permissions

- Python **3.10+** on **macOS, Linux, or WSL**. The client uses only the Python standard library. Native Windows file-permission handling is not supported.
- A GoDaddy [Personal Access Token](https://developer.godaddy.com/personal-access-token), required for v3. Classic key/secret credentials work with v1/v2 only.
- `domains.domain:read` for inventory and DNS reads; `domains.dns:update` for DNS record changes; `domains.nameserver:update` for nameserver replacement. Other operations need their documented scopes and account eligibility.
- **Optional:** 1Password CLI (`op`) for importing a PAT from your own item and field. No vault or account is assumed.
- No required environment variables. Credentials are read from `~/.config/godaddy/credentials.json`, or the global `--credentials PATH` option.
- Node.js/npm is needed only if you install using the `skills` CLI.

A successful GET establishes read capability, not a complete list of token scopes. Purchases, renewals, transfers, cancellation, and deletion require authorization for the exact domain, term, and cost.

## Install

Install into a project for both agents:

```bash
npx skills add joeeeeey/godaddy-ops --skill godaddy-ops --agent claude-code codex
```

Add `--global` if you prefer a user-level installation. The repository has a standard root `SKILL.md`; both agents use the same instructions and Python helpers. `agents/openai.yaml` is optional Codex display metadata.

[Browse on skills.sh](https://skills.sh/joeeeeey/godaddy-ops/godaddy-ops).

## Credentials

Create a private directory with mode `0700` and a credential file with mode `0600`. Use a local editor or secret manager; never paste real tokens into agent chats, shell arguments, or this repository.

PAT credential-file structure (placeholder only):

```json
{"auth_type":"pat","token":"<personal-access-token>"}
```

Classic credential-file structure:

```json
{"auth_type":"sso-key","key":"<classic-key>","secret":"<classic-secret>"}
```

With 1Password, run from the installed skill directory:

```bash
python3 scripts/import_1password.py --item 'GoDaddy API' --vault 'Infrastructure' --field token
```

Supply your own item, vault, and field. The importer prints no secret values and refuses ambiguous fields or overwriting an existing file unless `--replace` is supplied.

## Operator reference

Run these commands from the installed skill directory:

```bash
python3 scripts/godaddy.py domains
python3 scripts/godaddy.py domains --format json
python3 scripts/godaddy.py domain example.com
python3 scripts/godaddy.py dns example.com
python3 scripts/godaddy.py request GET /v3/domains/check-availability --query domain=example.com
```

For OTE testing, put `--environment ote --credentials /path/to/ote-credentials.json` before the subcommand. OTE uses separately issued credentials; production is the default.

For a nameserver change, write the exact hostname array into a local JSON file, then preview it:

```bash
python3 scripts/godaddy.py request PUT \
  /v3/domains/domain-names/example.com/nameservers \
  --body-file /tmp/nameservers.json \
  --idempotency-key 68cf469c-fdb0-4605-87ed-3fda32d814fc
```

Generate a **new UUID for each logical change**; the example key is illustrative. After authorization, add `--execute` to the same command. Nameserver writes require `Idempotency-Key`, return an asynchronous operation, and need read-back verification. Prepare DNS at the destination before changing delegation.

The client refuses credential-file symlinks and group/world-readable files, restricts requests to the selected GoDaddy API origin, rejects redirects, and prevents pagination from leaving the original collection. It never automatically retries requests. DNS `PUT` replaces a complete record; preserve all relevant fields. An uncertain write result requires reading current state before retrying.

## Validation

```bash
python3 scripts/test_godaddy.py
python3 scripts/test_import_1password.py
```

All tests use synthetic credentials and mocked API/1Password responses. They do not contact GoDaddy. A live read-only smoke test is `python3 scripts/godaddy.py domains` after you configure credentials. No private account snapshots or tokens are distributed.

See [API notes](references/api.md) for endpoint behavior, scopes, pagination, errors, and official sources.

## License

MIT. This is an independent community project and is not affiliated with GoDaddy.
