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
- Configure either environment variables (`GODADDY_PAT`, or `GODADDY_KEY` + `GODADDY_SECRET`) or a private `~/.config/godaddy/credentials.json` file. No password-manager software is required.
- Node.js/npm is needed only if you install using the `skills` CLI.

A successful GET establishes read capability, not a complete list of token scopes. Purchases, renewals, transfers, cancellation, and deletion require authorization for the exact domain, term, and cost.

## Install

Install into a project for both agents:

```bash
npx skills add joeeeeey/godaddy-ops --skill godaddy-ops --agent claude-code codex
```

Add `--global` if you prefer a user-level installation. The repository has a standard root `SKILL.md`; both agents use the same instructions and Python helpers. `agents/openai.yaml` is optional Codex display metadata.

[Browse on skills.sh](https://skills.sh/joeeeeey/godaddy-ops/godaddy-ops).

## Credential setup

Choose either environment variables or a config file. Use your own [GoDaddy PAT](https://developer.godaddy.com/personal-access-token). Never paste real tokens into agent chats, command arguments, or this repository.

### Option 1: environment variables

Set `GODADDY_PAT` for PAT authentication. For example, in a local Bash/Zsh terminal, enter it with hidden input so the value is not recorded in shell history:

```bash
read -rs GODADDY_PAT
export GODADDY_PAT
```

The first command waits for you to enter the PAT locally. For classic credentials, set both `GODADDY_KEY` and `GODADDY_SECRET` instead:

```bash
read -rs GODADDY_KEY
read -rs GODADDY_SECRET
export GODADDY_KEY GODADDY_SECRET
```

You can also inject these variables using your existing CI or runtime configuration. `GODADDY_PAT` takes precedence over classic credentials if both are present. Empty PATs or incomplete key/secret pairs fail without silently switching accounts.

### Option 2: config file

Create `~/.config/godaddy/credentials.json` using a local editor. Set the directory to mode `0700` and the file to mode `0600`, owned by your user. The JSON formats below contain placeholders, not real credentials.

PAT:

```json
{"auth_type":"pat","token":"<personal-access-token>"}
```

Classic key/secret:

```json
{"auth_type":"sso-key","key":"<classic-key>","secret":"<classic-secret>"}
```

To use another file:

```bash
python3 scripts/godaddy.py --credentials /path/to/credentials.json domains
```

**Selection order:** explicit `--credentials PATH` > environment variables > default config file. An explicit file is useful when switching accounts or using OTE while production credentials are present in the environment.

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
```

All tests use synthetic credentials and mocked API responses. They do not contact GoDaddy. A live read-only smoke test is `python3 scripts/godaddy.py domains` after you configure credentials. No private account snapshots or tokens are distributed.

See [API notes](references/api.md) for endpoint behavior, scopes, pagination, errors, and official sources.

## License

MIT. This is an independent community project and is not affiliated with GoDaddy.
