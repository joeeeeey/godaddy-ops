#!/usr/bin/env python3
"""Offline tests: no real credentials and no network calls."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import godaddy as g


class FakeClient:
    base = g.BASES['production']
    def __init__(self, pages):
        self.pages = iter(pages)
        self.urls = []
    def request(self, method, path):
        self.urls.append(path)
        return next(self.pages), 200, {}


class Tests(unittest.TestCase):
    def test_follow_v3_pages(self):
        c = FakeClient([
            {'items': [{'domain': 'a.com'}], 'links': [{'rel': 'next', 'href': '?pageToken=abc'}]},
            {'items': [{'domain': 'b.com'}], 'links': []},
        ])
        self.assertEqual([x['domain'] for x in g.collection(c, '/v3/domains/domain-names')], ['a.com', 'b.com'])
        self.assertEqual(c.urls[1], c.base + '/v3/domains/domain-names?pageToken=abc')

    def test_pagination_cannot_leak_credentials(self):
        for href in ['https://evil.example/v3/domains', '//evil.example/v3/domains', '/v3/unrelated', '/v3/domains/domain-names']:
            with self.subTest(href=href):
                c = FakeClient([{'items': [], 'links': [{'rel': 'next', 'href': href}]}])
                with self.assertRaises(g.Failure):
                    g.collection(c, '/v3/domains/domain-names')
                self.assertEqual(len(c.urls), 1)

    def test_partial_collection_is_not_success(self):
        c = FakeClient([{'items': [], 'links': [{'rel': 'next', 'href': ''}]}])
        with self.assertRaises(g.Failure):
            g.collection(c, '/v3/domains/domain-names')

    def test_v1_marker_and_exact_page_boundary(self):
        page = [{'domain': f'd{i}.com'} for i in range(100)]
        c = FakeClient([page, []])
        self.assertEqual(len(g.domains_v1(c)), 100)
        self.assertIn('marker=d99.com', c.urls[1])

    def test_write_preview_needs_no_credentials_or_network(self):
        for method in ('PUT', 'POST', 'PATCH', 'DELETE'):
            out = io.StringIO()
            with patch.object(g, 'Client', side_effect=AssertionError('must not create client')), contextlib.redirect_stdout(out):
                g.main(['request', method, '/v1/domains/example.com'])
            self.assertTrue(json.loads(out.getvalue())['dry_run'])

    def test_credential_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'credentials.json'
            p.write_text(json.dumps({'auth_type': 'pat', 'token': 'FAKE_TEST_TOKEN'}))
            p.chmod(0o600)
            self.assertEqual(g.credentials(p), ('pat', 'Bearer FAKE_TEST_TOKEN'))
            p.chmod(0o644)
            with self.assertRaises(g.Failure):
                g.credentials(p)

    def test_environment_pat_precedes_default_file_and_classic_environment(self):
        with patch.dict(os.environ, {'GODADDY_PAT': 'SYNTHETIC_ENV_PAT', 'GODADDY_KEY': 'SYNTHETIC_KEY', 'GODADDY_SECRET': 'SYNTHETIC_SECRET'}, clear=True), patch.object(g.os, 'open', side_effect=AssertionError('must not read file')):
            self.assertEqual(g.credentials(), ('pat', 'Bearer SYNTHETIC_ENV_PAT'))

    def test_complete_classic_environment(self):
        with patch.dict(os.environ, {'GODADDY_KEY': 'SYNTHETIC_KEY', 'GODADDY_SECRET': 'SYNTHETIC_SECRET'}, clear=True):
            self.assertEqual(g.credentials(), ('sso-key', 'sso-key SYNTHETIC_KEY:SYNTHETIC_SECRET'))

    def test_incomplete_or_empty_environment_does_not_silently_fall_back(self):
        for environment in [{'GODADDY_KEY': 'SYNTHETIC_KEY'}, {'GODADDY_SECRET': 'SYNTHETIC_SECRET'}, {'GODADDY_PAT': ''}]:
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True), patch.object(g.os, 'open', side_effect=AssertionError('must not fall back')):
                with self.assertRaises(g.Failure):
                    g.credentials()

    def test_explicit_file_overrides_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'credentials.json'
            p.write_text(json.dumps({'auth_type': 'pat', 'token': 'SYNTHETIC_FILE_PAT'}))
            p.chmod(0o600)
            with patch.dict(os.environ, {'GODADDY_PAT': 'SYNTHETIC_ENV_PAT'}, clear=True):
                self.assertEqual(g.credentials(p), ('pat', 'Bearer SYNTHETIC_FILE_PAT'))

    def test_default_file_used_without_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'credentials.json'
            p.write_text(json.dumps({'auth_type': 'pat', 'token': 'SYNTHETIC_FILE_PAT'}))
            p.chmod(0o600)
            with patch.dict(os.environ, {}, clear=True), patch.object(g, 'DEFAULT_CREDENTIALS', p):
                self.assertEqual(g.credentials(), ('pat', 'Bearer SYNTHETIC_FILE_PAT'))

    def test_explicit_write_sent_once_and_preserves_async_location(self):
        client = g.Client.__new__(g.Client)
        client.base = g.BASES['production']
        client.kind, client.authorization, client.calls = 'pat', 'Bearer FAKE_TEST_TOKEN', 0
        from unittest.mock import MagicMock
        client.opener = MagicMock()
        response = client.opener.open.return_value.__enter__.return_value
        response.read.return_value = b'{"status":"PENDING"}'
        response.status = 202
        response.headers = {'Location': '/v3/domains/operations/123'}
        out = io.StringIO()
        with patch.object(g, 'Client', return_value=client), contextlib.redirect_stdout(out):
            g.main(['request', 'PUT', '/v3/domains/domain-names/example.com/nameservers', '--idempotency-key', '12345678-1234-1234-1234-123456789abc', '--execute'])
        result = json.loads(out.getvalue())
        self.assertEqual(result['status'], 202)
        self.assertEqual(result['headers']['Location'], '/v3/domains/operations/123')
        self.assertEqual(client.opener.open.call_count, 1)
        self.assertEqual(client.opener.open.call_args.args[0].method, 'PUT')
        self.assertEqual(client.opener.open.call_args.args[0].get_header('Idempotency-key'), '12345678-1234-1234-1234-123456789abc')

    def test_nameserver_write_requires_idempotency_before_network(self):
        c = g.Client.__new__(g.Client)
        c.base, c.kind, c.authorization = g.BASES['production'], 'pat', 'Bearer FAKE'
        with self.assertRaisesRegex(g.Failure, 'require --idempotency-key'):
            c.request('PUT', '/v3/domains/domain-names/example.com/nameservers', ['ns1.example.com', 'ns2.example.com'])

    def test_429_empty_body_and_no_retry(self):
        from unittest.mock import MagicMock
        c = g.Client.__new__(g.Client)
        c.base, c.kind, c.authorization, c.calls = g.BASES['production'], 'pat', 'Bearer FAKE', 0
        c.opener = MagicMock()
        c.opener.open.side_effect = HTTPError(c.base, 429, 'rate limited', {'RateLimit-Reset': '120'}, io.BytesIO(b''))
        with self.assertRaisesRegex(g.Failure, 'HTTP 429.*120s'):
            c.request('GET', '/v3/domains/domain-names')
        self.assertEqual(c.opener.open.call_count, 1)

    def test_classic_cannot_call_v3(self):
        c = g.Client.__new__(g.Client)
        c.base, c.kind = g.BASES['production'], 'sso-key'
        with self.assertRaisesRegex(g.Failure, 'requires a PAT'):
            c.request('GET', '/v3/domains/domain-names')

    def test_redirects_are_rejected(self):
        self.assertIsNone(g.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example'))


if __name__ == '__main__':
    unittest.main()
