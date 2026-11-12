import sys
from pathlib import Path
import types
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import rastisi_edge_probe as E


class EdgeProbeTests(unittest.TestCase):
    def test_tls_is_verified_for_real_hostname_but_connection_is_loopback(self):
        with patch.object(E.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout='ok')) as run:
            self.assertEqual(E.fetch('example.test',443,'/'), 'ok')
        args = run.call_args.args[0]
        self.assertIn('example.test:443:127.0.0.1',args)
        self.assertIn('https://example.test:443/',args)
        self.assertNotIn('-k',args)
        self.assertNotIn('--insecure',args)

    def test_invalid_certificate_or_missing_static_asset_blocks(self):
        with patch.object(E.subprocess,'run',return_value=types.SimpleNamespace(returncode=60,stdout='')):
            with self.assertRaises(ValueError): E.check('example.test',443)
        with patch.object(E,'fetch',return_value='<html>no assets</html>'):
            with self.assertRaisesRegex(ValueError,'static asset'): E.check('example.test',443)

    def test_host_injection_is_rejected(self):
        with self.assertRaises(ValueError): E.check('host/../../path',443)
