"""Manual/CI smoke of a downloaded arm64 app on an Apple Silicon Mac.
Launches the native executable, checks process/backend health and archive round trip.
Optional screenshot is evidence for manual review, not automated UI correctness.
Does not invoke file dialogs, bypass Gatekeeper, or change security settings.
"""
from pathlib import Path
import json
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request


def main():
    if sys.platform!='darwin' or platform.machine()!='arm64':
        raise SystemExit('Requires a real Apple Silicon macOS environment.')
    app=Path(sys.argv[1]).resolve()
    screenshot=Path(sys.argv[2]).resolve() if len(sys.argv)>2 else None
    log=Path.home()/'Library/Logs/AHAS/app.log'
    prior=log.stat().st_size if log.exists() else 0
    with tempfile.TemporaryDirectory(prefix='ahas-native-smoke-') as tmp:
        root=Path(tmp);source=root/'Source';source.mkdir()
        content=b'AHAS packaged native runtime round-trip\n'*10000
        (source/'a.txt').write_bytes(content);(source/'b.txt').write_bytes(content)
        p=subprocess.Popen([str(app/'Contents/MacOS/AHAS')],start_new_session=True)
        try:
            deadline=time.monotonic()+45;url=None
            while time.monotonic()<deadline:
                if p.poll() is not None:raise RuntimeError('Native app exited during launch: '+str(p.returncode))
                result=subprocess.run(['/usr/sbin/lsof','-a','-p',str(p.pid),'-iTCP','-sTCP:LISTEN','-Fn'],capture_output=True,text=True)
                match=re.search(r'n127\.0\.0\.1:(\d+)',result.stdout)
                if match:
                    url='http://127.0.0.1:'+match[1];break
                time.sleep(.2)
            if not url:raise RuntimeError('Packaged native app did not open its loopback backend.')
            time.sleep(4)
            if p.poll() is not None:raise RuntimeError('Native app exited after backend startup.')
            with urllib.request.urlopen(url,timeout=10) as response:html=response.read().decode()
            assert 'Made by Ahas Nimsandu' in html and 'Media Optimizer' in html and '.ahas' in html
            token=re.search(r"token='([^']+)'",html)[1]
            def api(route,data=None):
                req=urllib.request.Request(url+'/api/'+route,data=None if data is None else json.dumps(data).encode(),headers={'X-CompactLocal-Token':token,'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=15) as response:return json.load(response)
            def job(data):
                api('start',data);end=time.monotonic()+60
                while time.monotonic()<end:
                    state=api('status')
                    if state['status']!='running':
                        assert state['status']=='complete',state
                        return state['result']
                    time.sleep(.1)
                raise RuntimeError('Packaged archive operation timed out.')
            archive=root/'sample.ahas';dest=root/'Restored'
            job(dict(operation='compress',inputs=[str(source)],output=str(archive),level=6))
            job(dict(operation='verify',archive=str(archive)))
            job(dict(operation='extract',archive=str(archive),output=str(dest)))
            assert (dest/'Source/a.txt').read_bytes()==content
            assert (dest/'Source/b.txt').read_bytes()==content
            if screenshot:
                screenshot.parent.mkdir(parents=True,exist_ok=True)
                capture=subprocess.run(['/usr/sbin/screencapture','-x',str(screenshot)],capture_output=True,text=True,timeout=15)
                print('Screenshot:', 'captured for review' if capture.returncode==0 else 'unavailable: '+capture.stderr.strip())
            print('PASS: downloaded native app remains running; branded backend; bundled-runtime .ahas create/verify/extract; exact restored bytes.')
            print('This does not automate native file dialogs, Gatekeeper/quarantine approvals, or all GUI/media behavior.')
        except Exception:
            if log.exists():
                print('App log from this launch:',log.read_bytes()[prior:].decode(errors='replace')[-6000:])
            raise
        finally:
            if p.poll() is None:
                os.killpg(p.pid,signal.SIGTERM)
                try:p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid,signal.SIGKILL);p.wait()

if __name__=='__main__':main()
