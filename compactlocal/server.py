from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .ahas import compress, restore, Cancelled
from .media import optimize

ROOT = Path(__file__).parent
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.Lock()
JOB = {'status':'idle'}
CANCEL = threading.Event()
PREVIEW = False


def update(**kw):
    with LOCK:
        JOB.update(kw)


def run_job(data):
    try:
        op = data.get('operation')
        if op == 'compress':
            inputs = data.get('inputs')
            if not isinstance(inputs,list) or not all(isinstance(x,str) for x in inputs):
                raise ValueError('Inputs must be a list of file paths.')
            result = compress(inputs, data['output'], level=int(data.get('level',6)), progress=update, cancel=CANCEL)
        elif op == 'media':
            inputs = data.get('inputs')
            if not isinstance(inputs,list) or not all(isinstance(x,str) for x in inputs):
                raise ValueError('Inputs must be a list of file paths.')
            if data.get('accept_lossy') is not True:
                raise ValueError('Explicitly accept quality loss before using Media Optimizer.')
            result = optimize(inputs, data['output'], profile=data.get('profile','balanced'), media_type=data.get('media_type','auto'), progress=update, cancel=CANCEL)
        elif op in ('extract','verify'):
            limit = float(data.get('max_gb',1024))
            if not 0 < limit <= 1048576:
                raise ValueError('Choose a positive size limit up to 1,048,576 GiB.')
            result = restore(data['archive'], data.get('output'), verify=op=='verify',
                             max_bytes=int(limit*1024**3), progress=update, cancel=CANCEL)
        else:
            raise ValueError('Unknown operation.')
        update(status='complete',result=result,finished=time.time())
    except Cancelled as exc:
        update(status='cancelled',error=str(exc),finished=time.time())
    except Exception as exc:
        update(status='error',error=str(exc) or type(exc).__name__,finished=time.time())
        traceback.print_exc()


def dialog(kind):
    if sys.platform != 'darwin':
        raise ValueError('Native file pickers are available on macOS. In this preview, enter full paths instead.')
    scripts = {
        'files': 'set picked to choose file with prompt "Choose files to compress" with multiple selections allowed\nset itemsOut to {}\nrepeat with p in picked\nset end of itemsOut to POSIX path of p\nend repeat\nset AppleScript\'s text item delimiters to linefeed\nreturn itemsOut as text',
        'folder': 'return POSIX path of (choose folder with prompt "Choose a folder")',
        'archive': 'return POSIX path of (choose file with prompt "Choose a CompactLocal archive")',
        'save': 'return POSIX path of (choose file name with prompt "Save new archive outside your source folder" default name "Archive.ahas")',
    }
    if kind not in scripts:
        raise ValueError('Unknown picker.')
    # Static scripts only: no path or browser input is evaluated as AppleScript.
    result = subprocess.run(['osascript','-e',scripts[kind]], capture_output=True,text=True,timeout=300)
    if result.returncode:
        if '(-128)' in result.stderr:
            return []
        raise ValueError(result.stderr.strip() or 'Could not open macOS picker.')
    return [x for x in result.stdout.strip().splitlines() if x]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def allowed_host(self):
        host = self.headers.get('Host','').split(':')[0].lower()
        return host in ('localhost','127.0.0.1') or (PREVIEW and host.endswith('.e2b.app'))

    def send(self, code, body, content_type='application/json'):
        if not isinstance(body,bytes):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'" + ('' if PREVIEW else "; frame-ancestors 'none'"))
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        return self.allowed_host() and secrets.compare_digest(self.headers.get('X-CompactLocal-Token',''),TOKEN)

    def do_GET(self):
        if not self.allowed_host():
            return self.send(403,{'error':'Host not allowed'})
        if self.path == '/':
            if not PREVIEW and self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return self.send(403,{'error':'Open the app from its launcher.'})
            html = (ROOT/'index.html').read_text(encoding='utf-8').replace('__TOKEN__',TOKEN).replace('__ENV__','Hosted preview · files are in the demo workspace' if PREVIEW else 'Local on your Mac · no uploads')
            return self.send(200,html.encode(),'text/html; charset=utf-8')
        if self.path == '/api/status' and self.authorized():
            with LOCK:
                body = dict(JOB)
            body['now'] = time.time()
            return self.send(200,body)
        return self.send(404,{'error':'Not found'})

    def do_POST(self):
        if not self.authorized():
            return self.send(403,{'error':'Unauthorized request. Reopen the app.'})
        origin = self.headers.get('Origin')
        if origin and origin not in ('http://'+self.headers.get('Host',''),'https://'+self.headers.get('Host','')):
            return self.send(403,{'error':'Origin not allowed'})
        try:
            length = int(self.headers.get('Content-Length','0'))
            if length < 0 or length > 1024*1024:
                return self.send(413,{'error':'Request too large'})
            data = json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(data,dict):
                raise ValueError('Expected an object')
            if self.path == '/api/start':
                with LOCK:
                    if JOB.get('status') == 'running':
                        return self.send(409,{'error':'An operation is already running.'})
                    JOB.clear()
                    JOB.update(status='running',phase='Starting',done=0,total=0,started=time.time(),operation=data.get('operation'))
                    CANCEL.clear()
                threading.Thread(target=run_job,args=(data,),daemon=True).start()
                return self.send(200,{'ok':True})
            if self.path == '/api/cancel':
                CANCEL.set()
                return self.send(200,{'ok':True})
            if self.path == '/api/dialog':
                return self.send(200,{'paths':dialog(data.get('kind'))})
            return self.send(404,{'error':'Not found'})
        except Exception as exc:
            return self.send(400,{'error':str(exc)})


def main():
    global PREVIEW
    parser = argparse.ArgumentParser(description='AHAS: lossless archives and explicit lossy media optimization')
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--preview',action='store_true',help='Expose hosted sandbox preview; not for use on your Mac')
    parser.add_argument('--no-browser',action='store_true')
    args = parser.parse_args()
    PREVIEW = args.preview
    server = ThreadingHTTPServer(('0.0.0.0' if PREVIEW else '127.0.0.1', args.port),Handler)
    server.daemon_threads = True
    url = 'http://127.0.0.1:' + str(server.server_port)
    print('\nAHAS is running at ' + url + '\nKeep this window open. Press Control-C to quit.\n',flush=True)
    if not args.no_browser:
        threading.Timer(.4,lambda:webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        CANCEL.set()
        print('\nStopping; waiting for incomplete-output cleanup…',flush=True)
        deadline = time.monotonic()+120
        while time.monotonic() < deadline:
            with LOCK:
                running = JOB.get('status') == 'running'
            if not running:
                break
            time.sleep(.1)
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
