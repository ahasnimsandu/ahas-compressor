"""Explicitly lossy image/video optimization using macOS system tools.
Never changes source files. Keeps an original copy if a conversion is not smaller.
No ffmpeg downloads, hidden shell evaluation, or third-party runtime dependencies.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from .archive import ArchiveError, Cancelled, check_cancel, emit, scan

IMAGES = {'.jpg','.jpeg','.png','.tif','.tiff','.heic','.heif','.bmp'}
VIDEOS = {'.mov','.mp4','.m4v'}
PROFILES = {
    'smallest': dict(quality=55,pixels=1600,video=['Preset640x480','PresetLowQuality']),
    'balanced': dict(quality=72,pixels=2560,video=['Preset1280x720','PresetMediumQuality']),
    'quality': dict(quality=85,pixels=3840,video=['Preset1920x1080','PresetHighestQuality']),
}


def execute(command, cancel, progress, current):
    with tempfile.TemporaryFile() as log:
        p = subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True)
        last = 0
        try:
            while p.poll() is None:
                check_cancel(cancel)
                if time.monotonic()-last>1:
                    pos = os.fstat(log.fileno()).st_size
                    text = os.pread(log.fileno(),4096,max(0,pos-4096)).decode(errors='replace')
                    matches = re.findall(r'(\d+(?:\.\d+)?)\s*%',text)
                    if matches:
                        emit(progress,current=current,media_percent=min(100,float(matches[-1])))
                    last = time.monotonic()
                time.sleep(.15)
            log.seek(0,os.SEEK_END)
            length = log.tell()
            log.seek(max(0,length-8192))
            details = log.read().decode(errors='replace').strip()
            if p.returncode:
                raise ArchiveError(details or 'macOS conversion tool failed.')
        finally:
            if p.poll() is None:
                os.killpg(p.pid,signal.SIGTERM)
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid,signal.SIGKILL)
                    p.wait()


def video_preset(profile):
    p = subprocess.run(['/usr/bin/avconvert','--help'],capture_output=True,text=True,timeout=15)
    available = set(re.findall(r'Preset[A-Za-z0-9_]+',p.stdout+'\n'+p.stderr))
    for option in PROFILES[profile]['video']:
        if option in available:
            return option
    raise ArchiveError('The requested video presets are unavailable on this Mac. Try a different quality preset or use Lossless Archive.')


def optimize(inputs, output, profile='balanced', media_type='auto', progress=None, cancel=None):
    if sys.platform!='darwin':
        raise ArchiveError('Media Optimizer needs macOS system tools. It is not available in the Linux hosted preview.')
    if profile not in PROFILES or media_type not in ('auto','images','videos'):
        raise ArchiveError('Choose a valid media type and quality preset.')
    dest = Path(output).expanduser().absolute()
    if dest.exists() or not dest.parent.is_dir():
        raise ArchiveError('Choose a new, non-existing output folder inside an existing parent.')
    for src in inputs:
        p = Path(src).expanduser().resolve()
        if dest.resolve()==p or (p.is_dir() and dest.resolve().is_relative_to(p)):
            raise ArchiveError('Choose an output folder outside the source folders.')
    entries, skipped = scan(inputs,cancel)
    candidates = []
    for path,rel,kind,st in entries:
        if kind!='file':
            continue
        suffix = path.suffix.lower()
        typ = 'image' if suffix in IMAGES else 'video' if suffix in VIDEOS else None
        if not typ or (media_type=='images' and typ!='image') or (media_type=='videos' and typ!='video'):
            skipped.append(str(path)+' (not a selected/supported media type)')
        else:
            candidates.append((path,rel,typ,st))
    if not candidates:
        raise ArchiveError('No supported media found. Images: JPEG, PNG, TIFF, HEIC, BMP. Video containers: MP4, M4V, MOV; codec support depends on macOS. Audio-only files are not supported.')
    for _,_,typ,_ in candidates:
        tool = '/usr/bin/sips' if typ=='image' else '/usr/bin/avconvert'
        if not Path(tool).is_file():
            raise ArchiveError('Required macOS tool not found: '+tool)
    total = sum(st.st_size for _,_,_,st in candidates)
    if total>shutil.disk_usage(dest.parent).free:
        raise ArchiveError('Not enough free space for conservative media processing.')
    done = optimized = kept = saved = result_size = 0
    results = []
    used = set()
    created = False
    preset = None
    def reserve(relative):
        p = dest/relative
        name = p
        count = 2
        while str(name.relative_to(dest)).casefold() in used or name.exists():
            name = p.with_name(p.stem+'-'+str(count)+p.suffix)
            count += 1
        used.add(str(name.relative_to(dest)).casefold())
        name.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        return name
    try:
        dest.mkdir(mode=0o700)
        created = True
        for source,rel,typ,st in candidates:
            check_cancel(cancel)
            emit(progress,phase='Optimizing images / video (lossy)',current=rel,done=done,total=total,media_percent=0)
            if source.stat().st_size!=st.st_size or source.stat().st_mtime_ns!=st.st_mtime_ns:
                raise ArchiveError('Source changed: '+rel)
            error = None
            converted = None
            with tempfile.TemporaryDirectory(prefix='.ahas-media-',dir=dest) as tmp:
                ext = '.jpg' if typ=='image' else '.mov'
                tmp_output = Path(tmp)/('converted'+ext)
                try:
                    if typ=='image':
                        p = PROFILES[profile]
                        command = ['/usr/bin/sips','-s','format','jpeg','-s','formatOptions',str(p['quality']),'-Z',str(p['pixels']),str(source),'--out',str(tmp_output)]
                    else:
                        if preset is None:
                            preset = video_preset(profile)
                        command = ['/usr/bin/avconvert','--source',str(source),'--preset',preset,'--output',str(tmp_output),'--progress']
                    execute(command,cancel,progress,rel)
                    if not tmp_output.is_file() or tmp_output.stat().st_size==0:
                        raise ArchiveError('Conversion produced no usable output.')
                    if tmp_output.stat().st_size<st.st_size:
                        converted = reserve(str(Path(rel).with_name(Path(rel).stem+'-optimized'+ext)))
                        os.rename(tmp_output,converted)
                except Cancelled:
                    raise
                except Exception as exc:
                    error = str(exc)[:1500]
                check_cancel(cancel)
                if source.stat().st_size!=st.st_size or source.stat().st_mtime_ns!=st.st_mtime_ns:
                    raise ArchiveError('Source changed during conversion: '+rel)
                if converted is None:
                    converted = reserve(rel)
                    shutil.copyfile(source,converted)
                    kept += 1
                else:
                    optimized += 1
                size = converted.stat().st_size
                result_size += size
                saved += st.st_size-size
                done += st.st_size
                results.append(dict(source=rel,output=str(converted.relative_to(dest)),original_bytes=st.st_size,output_bytes=size,changed=size<st.st_size,error=error))
                emit(progress,phase='Optimizing images / video (lossy)',current=rel,done=done,total=total,media_percent=100)
        check_cancel(cancel)
        created = False
        emit(progress,phase='Complete',done=total,total=total)
        return dict(operation='media',output=str(dest),files=len(results),original_bytes=total,output_bytes=result_size,saved_bytes=saved,optimized=optimized,kept_original=kept,skipped=skipped,items=results,lossy=True,
                    warning='Quality, resolution, color/metadata, transparency, animation, audio tracks, and HDR may change. Converted files cannot restore the originals. Any file that failed or did not shrink was copied unchanged instead.')
    finally:
        if created:
            shutil.rmtree(dest)
