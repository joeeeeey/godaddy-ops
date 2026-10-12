#!/usr/bin/env python3
"""Export only an explicitly selected PAT field, without displaying its value."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--item', required=True, help='1Password item name or UUID')
    p.add_argument('--vault')
    p.add_argument('--field', required=True)
    p.add_argument('--section')
    p.add_argument('--output', type=Path, default=Path.home() / '.config/godaddy/credentials.json')
    p.add_argument('--replace', action='store_true')
    args = p.parse_args()
    target = args.output.expanduser()
    if target.is_symlink() or (target.exists() and not args.replace):
        raise ValueError('Output exists or is a symlink; use --replace only for an authorized local replacement.')
    cmd = ['op', 'item', 'get', args.item, '--format', 'json']
    if args.vault:
        cmd += ['--vault', args.vault]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError('1Password retrieval failed; check item/vault and approve the native unlock prompt.')
    item = json.loads(result.stdout)
    fields = [f for f in item.get('fields', []) if args.field in (f.get('id'), f.get('label'))
              and (not args.section or args.section in (f.get('section', {}).get('id'), f.get('section', {}).get('label')))]
    if len(fields) != 1:
        raise ValueError('Field missing or ambiguous; select its exact ID or section.')
    token = fields[0].get('value', '').strip()
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    if not token or any(c.isspace() for c in token):
        raise ValueError('Selected field is not a single PAT; no file was written.')
    if target.parent.is_symlink():
        raise ValueError('Credential directory must not be a symlink.')
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    target.parent.chmod(0o700)
    fd, temporary = tempfile.mkstemp(prefix='.credentials-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            os.fchmod(out.fileno(), 0o600)
            json.dump({'auth_type': 'pat', 'token': token}, out)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        if args.replace:
            os.replace(temporary, target)
        else:
            os.link(temporary, target)  # Atomic no-overwrite publication.
        print(f'Saved GoDaddy PAT to {target} (0600); credential value omitted.')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.TimeoutExpired):
        print('Credential import failed: verify item/field, unlock, output permissions, and overwrite intent. No secret output.', file=sys.stderr)
        sys.exit(1)
