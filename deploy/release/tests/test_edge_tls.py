"""Real loopback TLS: certificate validation and missing-static failure, no mocks."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest

PROBE = Path(__file__).resolve().parent.parent/'rastisi_edge_probe.py'


class LocalTLSProbeTests(unittest.TestCase):
    def test_verified_local_tls_and_static_asset_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            cert, key = Path(tmp)/'cert.pem', Path(tmp)/'key.pem'
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                            '-subj','/CN=edge.rastisi.test','-addext','subjectAltName=DNS:edge.rastisi.test',
                            '-keyout',str(key),'-out',str(cert)],capture_output=True,check=True)
            class Handler(BaseHTTPRequestHandler):
                missing_static = False
                def log_message(self,*args): pass
                def do_GET(self):
                    self.send_response(404 if self.path.startswith('/static/') and self.missing_static else 200)
                    payload = b'<html><script src="/static/probe.js"></script></html>'
                    self.send_header('Content-Length',str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
            server = HTTPServer(('127.0.0.1',0), Handler)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(cert,key)
            server.socket = ctx.wrap_socket(server.socket,server_side=True)
            thread = threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                cmd = [sys.executable,str(PROBE),'--host','edge.rastisi.test','--port',str(server.server_port)]
                env = dict(os.environ,CURL_CA_BUNDLE=str(cert))
                result = subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=30)
                if result.returncode:
                    diagnostic = subprocess.run(['curl','--silent','--show-error','--noproxy','edge.rastisi.test','--resolve','edge.rastisi.test:%d:127.0.0.1' % server.server_port,'https://edge.rastisi.test:%d/' % server.server_port],env=env,capture_output=True,text=True,timeout=20)
                    self.fail(result.stdout + result.stderr + diagnostic.stderr)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                Handler.missing_static = True
                result = subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,1)
                self.assertIn('static/probe.js',result.stdout)
                env.pop('CURL_CA_BUNDLE')
                result = subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,1,'self-signed certificate must fail without explicit trust')
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
