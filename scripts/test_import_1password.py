#!/usr/bin/env python3
"""Offline credential-import tests using synthetic 1Password responses."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import import_1password as importer

TOKEN = 'SYNTHETIC_PAT_NOT_A_REAL_SECRET'
OTHER = 'SYNTHETIC_UNRELATED_PASSWORD'


class Tests(unittest.TestCase):
    def invoke(self, target, fields=None, extra=None):
        fields = fields if fields is not None else [
            {'id': 'token', 'label': 'token', 'value': TOKEN},
            {'id': 'password', 'label': 'password', 'value': OTHER},
        ]
        response = subprocess.CompletedProcess([], 0, json.dumps({'fields': fields}), '')
        argv = ['import_1password.py', '--item', 'Test API', '--field', 'token', '--output', str(target)] + (extra or [])
        out = io.StringIO()
        with patch('sys.argv', argv), patch.object(importer.subprocess, 'run', return_value=response) as run, contextlib.redirect_stdout(out):
            importer.main()
        return out.getvalue(), run

    def test_only_selected_field_is_saved_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'private' / 'credentials.json'
            output, run = self.invoke(target)
            self.assertEqual(json.loads(target.read_text()), {'auth_type': 'pat', 'token': TOKEN})
            self.assertNotIn(TOKEN, output)
            self.assertNotIn(OTHER, output + target.read_text())
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(target.parent.stat().st_mode & 0o777, 0o700)
            self.assertNotIn(TOKEN, str(run.call_args))
            self.assertEqual(list(target.parent.glob('.credentials-*')), [])

    def test_existing_file_is_not_replaced_without_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'credentials.json'
            target.write_text('existing')
            with self.assertRaises(ValueError):
                self.invoke(target)
            self.assertEqual(target.read_text(), 'existing')

    def test_ambiguous_field_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'credentials.json'
            fields = [{'id': str(i), 'label': 'token', 'value': TOKEN} for i in range(2)]
            with self.assertRaises(ValueError):
                self.invoke(target, fields)
            self.assertFalse(target.exists())

    def test_symlink_is_not_followed_even_with_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / 'original'
            original.write_text('unchanged')
            target = Path(directory) / 'credentials.json'
            target.symlink_to(original)
            with self.assertRaises(ValueError):
                self.invoke(target, extra=['--replace'])
            self.assertEqual(original.read_text(), 'unchanged')

    def test_explicit_replacement_is_atomic_and_private(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'credentials.json'
            target.write_text('old')
            self.invoke(target, extra=['--replace'])
            self.assertEqual(json.loads(target.read_text())['token'], TOKEN)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
