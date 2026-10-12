#!/usr/bin/env python3
"""GoDaddy API client: explicit writes and paginated domain inventory."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlsplit, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler

DEFAULT_CREDENTIALS = Path.home() / '.config/godaddy/credentials.json'
BASES = {'production': 'https://api.godaddy.com', 'ote': 'https://api.ote-godaddy.com'}

class Failure(Exception):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def safe_url(base, path):
    url = urljoin(base + '/', path)
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc != urlsplit(base).netloc
            or parsed.fragment or not re.match(r'^/v[123]/', parsed.path)
            or '\\' in unquote(parsed.path)
            or any(s in ('.', '..') for s in unquote(parsed.path).split('/'))):
        raise Failure('Refusing destination outside the selected GoDaddy API.')
    return url

def credentials(path=None):
    data = None
    if path is None:
        if 'GODADDY_PAT' in os.environ:
            data = {'auth_type': 'pat', 'token': os.environ['GODADDY_PAT']}
        elif 'GODADDY_KEY' in os.environ or 'GODADDY_SECRET' in os.environ:
            data = {'auth_type': 'sso-key', 'key': os.environ.get('GODADDY_KEY'), 'secret': os.environ.get('GODADDY_SECRET')}
        else:
            path = DEFAULT_CREDENTIALS
    if data is None:
        try:
            fd = os.open(Path(path).expanduser(), os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd) as f:
                info = os.fstat(f.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                    raise Failure('Credential file must be owned by you with mode 0600.')
                data = json.load(f)
        except (OSError, ValueError):
            raise Failure('Cannot read credentials JSON; configure GODADDY_PAT or check credential-file path, format, and permissions.') from None
    if not isinstance(data, dict):
        raise Failure('Credentials must be a JSON object.')
    kind = data.get('auth_type', 'pat')
    fields = ['token'] if kind == 'pat' else ['key', 'secret'] if kind == 'sso-key' else []
    if not fields or any(not isinstance(data.get(k), str) or not data[k] or any(c.isspace() for c in data[k]) for k in fields):
        raise Failure('Invalid credential type or missing/malformed credential fields.')
    return kind, ('Bearer ' + data['token'] if kind == 'pat' else 'sso-key ' + data['key'] + ':' + data['secret'])

class Client:
    def __init__(self, base, credential_path):
        self.base = base
        self.kind, self.authorization = credentials(credential_path)
        self.opener = build_opener(NoRedirect())
        self.calls = 0

    def request(self, method, path, body=None, idempotency_key=None):
        url = safe_url(self.base, path)
        if self.kind == 'sso-key' and urlsplit(url).path.startswith('/v3/'):
            raise Failure('GoDaddy v3 requires a PAT; classic sso-key supports v1/v2 only.')
        headers = {'Authorization': self.authorization, 'Accept': 'application/json', 'User-Agent': 'godaddy-ops/1.0'}
        if idempotency_key is not None:
            if not re.fullmatch(r'[A-Za-z0-9_-]{16,64}', idempotency_key):
                raise Failure('Idempotency key must be 16-64 ASCII letters, digits, underscores, or hyphens.')
            headers['Idempotency-Key'] = idempotency_key
        if method != 'GET' and re.fullmatch(r'/v3/domains/domain-names/[^/]+/nameservers', urlsplit(url).path) and not idempotency_key:
            raise Failure('Nameserver updates require --idempotency-key (UUID recommended).')
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        req = Request(url, data=payload, headers=headers, method=method)
        self.calls += 1
        try:
            with self.opener.open(req, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else None, response.status, dict(response.headers)
        except HTTPError as error:
            try:
                detail = json.loads(error.read())
            except (ValueError, OSError):
                detail = {}
            if not isinstance(detail, dict):
                detail = {}
            code = str(detail.get('code', 'UNKNOWN'))
            # Upstream messages can reflect submitted secrets; do not dump bodies.
            if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', code):
                code = 'UNRECOGNIZED'
            retry = error.headers.get('Retry-After') or error.headers.get('RateLimit-Reset') or detail.get('retryAfterSec')
            delay = f'; retry delay={retry}s' if str(retry).isdigit() else ''
            raise Failure(f'GoDaddy HTTP {error.code}; code={code}{delay}. No automatic retry performed.') from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise Failure('Network/timeout/invalid JSON response. Write outcome may be uncertain; inspect state before retrying.') from None

def collection(client, path):
    items, visited = [], set()
    initial_path = urlsplit(safe_url(client.base, path)).path
    for _ in range(10000):
        url = safe_url(client.base, path)
        if url in visited or urlsplit(url).path != initial_path:
            raise Failure('Invalid/repeated pagination destination; inventory is incomplete.')
        visited.add(url)
        data, _, _ = client.request('GET', url)
        if not isinstance(data, dict) or not isinstance(data.get('items'), list):
            raise Failure('Expected a collection with items; inventory is incomplete.')
        if not all(isinstance(item, dict) for item in data['items']):
            raise Failure('Invalid collection item; inventory is incomplete.')
        items.extend(data['items'])
        links = data.get('links', [])
        if not isinstance(links, list) or not all(isinstance(link, dict) for link in links):
            raise Failure('Invalid pagination links; inventory is incomplete.')
        following = [link.get('href') for link in links if link.get('rel') == 'next']
        if not following:
            return items
        if len(following) != 1 or not isinstance(following[0], str) or not following[0]:
            raise Failure('Invalid next link; inventory is incomplete.')
        path = urljoin(url, following[0])
    raise Failure('Page limit exceeded; inventory is incomplete.')

def domains_v1(client):
    items, seen = [], set()
    marker = None
    for _ in range(10000):
        query = {'limit': 100}
        if marker:
            query['marker'] = marker
        page, _, _ = client.request('GET', '/v1/domains?' + urlencode(query))
        if not isinstance(page, list) or not all(isinstance(x, dict) and isinstance(x.get('domain'), str) for x in page):
            raise Failure('Expected a domain array; inventory is incomplete.')
        items.extend(page)
        if len(page) < 100:
            return items
        marker = page[-1]['domain']
        if marker in seen:
            raise Failure('Repeated marker; inventory is incomplete.')
        seen.add(marker)
    raise Failure('Page limit exceeded; inventory is incomplete.')

def segment(value):
    if not value or value in ('.', '..') or any(c in value for c in '/\\?#'):
        raise Failure('Invalid resource identifier.')
    return quote(value, safe='')

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials', help='Explicit config file; overrides environment credentials. Default file is ~/.config/godaddy/credentials.json.')
    parser.add_argument('--environment', choices=BASES, default='production')
    sub = parser.add_subparsers(dest='command', required=True)
    listing = sub.add_parser('domains', help='List every domain, following all pages')
    listing.add_argument('--api-version', choices=['auto', 'v1', 'v3'], default='auto')
    listing.add_argument('--format', choices=['table', 'json'], default='table')
    detail = sub.add_parser('domain')
    detail.add_argument('domain')
    detail.add_argument('--customer-id')
    dns = sub.add_parser('dns')
    dns.add_argument('zone')
    request = sub.add_parser('request', help='GET immediately; other methods preview unless --execute')
    request.add_argument('method', choices=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
    request.add_argument('path')
    request.add_argument('--query', action='append', default=[], metavar='KEY=VALUE')
    request.add_argument('--body-file', type=Path)
    request.add_argument('--execute', action='store_true')
    request.add_argument('--idempotency-key', help='Stable UUID for one logical mutation; required for v3 nameserver updates')
    args = parser.parse_args(argv)
    base = BASES[args.environment]
    if args.command == 'request':
        path = safe_url(base, args.path)
        pairs = []
        for entry in args.query:
            if '=' not in entry:
                raise Failure('--query requires KEY=VALUE.')
            pairs.append(entry.split('=', 1))
        if pairs:
            path += ('&' if '?' in path else '?') + urlencode(pairs)
        body = json.loads(args.body_file.read_text()) if args.body_file else None
        if args.method == 'GET' and args.body_file:
            raise Failure('GET does not accept --body-file.')
        if args.method != 'GET' and not args.execute:
            print(json.dumps({'dry_run': True, 'method': args.method, 'url': path, 'body': body, 'idempotency_key': args.idempotency_key}, indent=2))
            return
    client = Client(base, args.credentials)
    if args.command == 'domains':
        version = args.api_version if args.api_version != 'auto' else ('v3' if client.kind == 'pat' else 'v1')
        entries = collection(client, '/v3/domains/domain-names') if version == 'v3' else domains_v1(client)
        rows = []
        for item in entries:
            if not isinstance(item.get('domain'), str) or not item['domain']:
                raise Failure('Domain name missing; inventory is incomplete.')
            rows.append({'domain': item['domain'], 'status': item.get('status'), 'expires': item.get('expiresAt', item.get('expires')), 'autoRenew': item.get('autoRenew', item.get('renewAuto'))})
        if len({row['domain'] for row in rows}) != len(rows):
            raise Failure('Duplicate domains across pages; rerun for a consistent inventory.')
        rows.sort(key=lambda row: row['domain'])
        result = {'environment': args.environment, 'apiVersion': version, 'count': len(rows), 'pages': client.calls, 'domains': rows}
        if args.format == 'json':
            print(json.dumps(result, indent=2))
        else:
            print(f'{args.environment} | {version} | {len(rows)} domains | {client.calls} pages')
            print('DOMAIN\tSTATUS\tEXPIRES\tAUTO_RENEW')
            for row in rows:
                print('\t'.join('unknown' if v is None else str(v) for v in row.values()))
    elif args.command == 'dns':
        print(json.dumps(collection(client, '/v3/domains/zones/' + segment(args.zone) + '/dns-records'), indent=2))
    else:
        if args.command == 'domain':
            path = '/v1/domains/' + segment(args.domain)
            if args.customer_id:
                path = '/v2/customers/' + segment(args.customer_id) + '/domains/' + segment(args.domain)
            method, body = 'GET', None
        else:
            method = args.method
        key = args.idempotency_key if args.command == 'request' else None
        data, status, headers = client.request(method, path, body, idempotency_key=key)
        metadata = {k: v for k, v in headers.items() if k.lower() in ('location', 'retry-after', 'ratelimit-remaining', 'ratelimit-reset', 'x-request-id')}
        print(json.dumps({'status': status, 'headers': metadata, 'data': data}, indent=2))

if __name__ == '__main__':
    try:
        main()
    except Failure as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError):
        print('Error: cannot read input file or invalid JSON.', file=sys.stderr)
        sys.exit(1)
