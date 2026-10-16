import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from compactlocal import server


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.url = 'http://127.0.0.1:'+str(cls.http.server_port)
        cls.thread = threading.Thread(target=cls.http.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()

    def request(self,path,data=None,token=True,headers=None):
        h = {'Content-Type':'application/json'}
        if token:
            h['X-CompactLocal-Token'] = server.TOKEN
        h.update(headers or {})
        req = Request(self.url+path,data=None if data is None else json.dumps(data).encode(),headers=h)
        return urlopen(req,timeout=10)

    def test_html_has_no_external_assets(self):
        with self.request('/') as response:
            html = response.read().decode()
            self.assertIn('AHAS',html)
            self.assertIn(server.TOKEN,html)
            self.assertNotIn('__TOKEN__',html)
            self.assertNotIn('<script src=',html)
            self.assertNotIn('fonts.googleapis',html)
            self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])

    def test_no_token_rejected(self):
        with self.assertRaises(HTTPError) as exc:
            self.request('/api/start',{'operation':'verify'},token=False)
        self.assertEqual(exc.exception.code,403)

    def test_bad_host_rejected(self):
        with self.assertRaises(HTTPError) as exc:
            self.request('/',headers={'Host':'attacker.example'})
        self.assertEqual(exc.exception.code,403)

    def test_cross_origin_rejected(self):
        with self.assertRaises(HTTPError) as exc:
            self.request('/api/start',{},headers={'Origin':'https://attacker.example'})
        self.assertEqual(exc.exception.code,403)

    def test_http_compress_verify_extract(self):
        def wait():
            deadline = time.monotonic()+10
            while time.monotonic()<deadline:
                with self.request('/api/status') as r:
                    status = json.load(r)
                if status['status']!='running':
                    self.assertEqual(status['status'],'complete',status)
                    return status
                time.sleep(.02)
            self.fail('Job timed out')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root/'input.txt'
            data.write_bytes(b'local app integration\n'*10000)
            arc = root/'output.ahas'
            with self.request('/api/start',dict(operation='compress',inputs=[str(data)],output=str(arc))):
                pass
            status = wait()
            self.assertEqual(status['result']['files'],1)
            with self.request('/api/start',dict(operation='verify',archive=str(arc))):
                pass
            self.assertTrue(wait()['result']['verified'])
            dest = root/'Restored'
            with self.request('/api/start',dict(operation='extract',archive=str(arc),output=str(dest))):
                pass
            wait()
            self.assertEqual(data.read_bytes(),(dest/'input.txt').read_bytes())

    def test_media_requires_explicit_consent(self):
        from unittest.mock import patch
        with patch.object(server,'optimize') as convert, patch.object(server.traceback,'print_exc'):
            server.run_job(dict(operation='media',inputs=['unused'],output='unused',accept_lossy=False))
        convert.assert_not_called()
        self.assertIn('Explicitly accept',server.JOB['error'])
