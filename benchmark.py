"""Deterministic synthetic benchmark. Run: python3 benchmark.py > benchmark-results.json
Compares AHAS v2 balanced (solid XZ-6), legacy CLA XZ-3/chunk dedup, and ZIP/DEFLATE-6.
Selected cases are illustrative, not proof of universal superiority.
"""
import json
import platform
from pathlib import Path
import random
import tempfile
import time
import zipfile
from compactlocal.ahas import compress, restore
from compactlocal.archive import compress as legacy_compress


def run():
    results=[];rng=random.Random(20261017)
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        for case in ('zero-filled','duplicate-binaries','unique-random','repetitive-text','already-compressed','many-small-text-files'):
            source=root/case;source.mkdir()
            if case=='zero-filled':
                with (source/'zeros.bin').open('wb') as f:f.truncate(64*1024**2)
            elif case=='duplicate-binaries':
                data=rng.randbytes(1024**2)
                for i in range(16):(source/f'copy-{i:02d}.bin').write_bytes(data)
            elif case=='unique-random':(source/'random.bin').write_bytes(rng.randbytes(8*1024**2))
            elif case=='repetitive-text':(source/'app.log').write_bytes(b'2026-10-17 INFO request=success status=200 endpoint=/api/local\n'*100000)
            elif case=='already-compressed':
                with zipfile.ZipFile(source/'packed.zip','w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('random.bin',rng.randbytes(4*1024**2))
            else:
                for i in range(150):(source/f'file-{i:03d}.txt').write_text(('Document '+str(i)+'\n')+('A shared paragraph of documentation and comments.\n'*40))
            arc=root/(case+'.ahas');start=time.perf_counter();r=compress([source],arc);new_time=time.perf_counter()-start
            start=time.perf_counter();restore(arc,verify=True);verify_time=time.perf_counter()-start
            old=root/(case+'.cla');start=time.perf_counter();legacy_compress([source],old);old_time=time.perf_counter()-start
            zpath=root/(case+'.zip');start=time.perf_counter()
            with zipfile.ZipFile(zpath,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
                for f in sorted(source.rglob('*')):
                    if f.is_file():z.write(f,str(f.relative_to(root)))
            zip_time=time.perf_counter()-start
            results.append(dict(case=case,original_bytes=r['original_bytes'],ahas_v2_bytes=arc.stat().st_size,legacy_cla_bytes=old.stat().st_size,zip_deflate6_bytes=zpath.stat().st_size,ahas_seconds=round(new_time,4),legacy_seconds=round(old_time,4),zip_seconds=round(zip_time,4),verify_seconds=round(verify_time,4),verified=True))
    return dict(python=platform.python_version(),platform=platform.platform(),note='Selected synthetic cases. Codec/preset/container differences all contribute. AHAS fingerprints files before packing; this cost is included. No media-quality comparison and no claim to beat all compressors.',results=results)

if __name__=='__main__':print(json.dumps(run(),indent=2))
