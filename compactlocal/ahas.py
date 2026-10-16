"""AHAS v2: self-contained solid XZ stream, whole-file deduplication, zero runs.
Not a novel codec. Legacy SQLite .cla archives remain readable via archive.py.
"""
from __future__ import annotations
import hashlib
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import struct
import tempfile
import unicodedata
from . import archive as legacy
from .archive import ArchiveError, Cancelled, check_cancel, emit, safe_name, scan

MAGIC = b'AHAS\x02\r\n\x1a'
CHUNK = 4 * 1024 * 1024
JSON_LIMIT = 1024 * 1024


def dump(stream, kind, obj):
    data = json.dumps(obj, ensure_ascii=True, separators=(',', ':')).encode()
    if len(data) > JSON_LIMIT:
        raise ArchiveError('Archive metadata record is too large.')
    stream.write(kind + struct.pack('>I', len(data)) + data)


class XZReader:
    def __init__(self, source):
        self.source = source
        self.decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=256 * 1024**2)
        self.buffer = bytearray()
        self.finished = False

    def read(self, size):
        if size < 0 or size > CHUNK:
            raise ArchiveError('Invalid read size.')
        while len(self.buffer) < size and not self.finished:
            data = self.source.read(65536) if self.decoder.needs_input else b''
            if not data and self.decoder.needs_input:
                raise ArchiveError('Truncated AHAS compressed stream.')
            raw = self.decoder.decompress(data, max_length=max(65536, size-len(self.buffer)))
            self.buffer.extend(raw)
            if self.decoder.eof:
                if self.decoder.unused_data or self.source.read(1):
                    raise ArchiveError('Unexpected trailing data after AHAS stream.')
                self.finished = True
        out = bytes(self.buffer[:size])
        del self.buffer[:size]
        return out


def exact(stream, n):
    data = stream.read(n)
    if len(data) != n:
        raise ArchiveError('Truncated AHAS record.')
    return data


def load(stream):
    size = struct.unpack('>I',exact(stream,4))[0]
    if size > JSON_LIMIT:
        raise ArchiveError('Oversized AHAS metadata.')
    obj = json.loads(exact(stream,size))
    if not isinstance(obj,dict):
        raise ArchiveError('Invalid AHAS metadata.')
    return obj


def open_source(path, st):
    fd = os.open(path,os.O_RDONLY | getattr(os,'O_NOFOLLOW',0) | getattr(os,'O_NONBLOCK',0))
    f = os.fdopen(fd,'rb')
    now = os.fstat(f.fileno())
    if not stat.S_ISREG(now.st_mode) or (now.st_dev,now.st_ino,now.st_size,now.st_mtime_ns) != (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns):
        f.close()
        raise ArchiveError('Source changed: '+str(path))
    return f


def compress(inputs, output, level=6, progress=None, cancel=None):
    if level not in (1,6,9):
        raise ArchiveError('Choose compression level 1, 6, or 9.')
    if not inputs:
        raise ArchiveError('Choose files or folders first.')
    output = Path(output).expanduser().absolute()
    if output.suffix.lower() != '.ahas':
        output = Path(str(output)+'.ahas')
    for source in inputs:
        src = Path(source).expanduser().resolve()
        if output.resolve()==src or (src.is_dir() and output.resolve().is_relative_to(src)):
            raise ArchiveError('Save the archive outside selected source folders.')
    if output.exists():
        raise ArchiveError('Output exists; choose a new archive name.')
    if not output.parent.is_dir():
        raise ArchiveError('Output parent folder does not exist.')
    emit(progress,phase='Scanning sources',current='')
    entries, skipped = scan(inputs,cancel)
    total = sum(st.st_size for _,_,kind,st in entries if kind=='file')
    emit(progress,phase='Fingerprinting for duplicates',done=0,total=total)
    fingerprints = {}
    done = 0
    for path,rel,kind,st in entries:
        if kind!='file':
            continue
        h = hashlib.blake2b(digest_size=32)
        size = 0
        with open_source(path,st) as f:
            while True:
                check_cancel(cancel)
                raw = f.read(CHUNK)
                if not raw:
                    break
                size += len(raw)
                h.update(raw)
                done += len(raw)
                emit(progress,phase='Fingerprinting for duplicates',done=done,total=total,current=rel)
            if size!=st.st_size or os.fstat(f.fileno()).st_mtime_ns!=st.st_mtime_ns:
                raise ArchiveError('Source changed while fingerprinting: '+rel)
        fingerprints[rel] = h.digest()
    fd,temp = tempfile.mkstemp(prefix='.ahas-',suffix='.partial',dir=output.parent)
    os.close(fd)
    seen = {}
    done = dedup = zeros = files = 0
    try:
        with open(temp,'wb') as target:
            target.write(MAGIC)
            # One compressor/dictionary for the entire archive, not one per chunk.
            with lzma.LZMAFile(target,'wb',format=lzma.FORMAT_XZ,preset=level | (lzma.PRESET_EXTREME if level==9 else 0)) as stream:
                dump(stream,b'H',dict(version=2,total=total,entries=len(entries)))
                for path,rel,kind,st in entries:
                    check_cancel(cancel)
                    meta = dict(path=rel,size=st.st_size if kind=='file' else 0,mode=stat.S_IMODE(st.st_mode),mtime_ns=st.st_mtime_ns)
                    if kind=='dir':
                        dump(stream,b'D',meta)
                        continue
                    digest = fingerprints[rel]
                    meta['digest'] = digest.hex()
                    key = (st.st_size,digest)
                    # Re-check metadata even for files whose bytes are deduplicated.
                    with open_source(path,st) as source:
                        if key in seen:
                            meta['source'] = seen[key]
                            dump(stream,b'R',meta)
                            dedup += st.st_size
                            done += st.st_size
                        else:
                            dump(stream,b'F',meta)
                            read = 0
                            h = hashlib.blake2b(digest_size=32)
                            while True:
                                check_cancel(cancel)
                                raw = source.read(CHUNK)
                                if not raw:
                                    break
                                read += len(raw)
                                if read > st.st_size:
                                    raise ArchiveError('Source grew while packing: '+rel)
                                h.update(raw)
                                if not raw.strip(b'\0'):
                                    stream.write(b'Z'+struct.pack('>I',len(raw)))
                                    zeros += len(raw)
                                else:
                                    stream.write(b'B'+struct.pack('>I',len(raw))+raw)
                                done += len(raw)
                                emit(progress,phase='Solid compression',done=done,total=total,current=rel,deduplicated=dedup,zero_bytes=zeros,archive_bytes=target.tell())
                            if read!=st.st_size or h.digest()!=digest or os.fstat(source.fileno()).st_mtime_ns!=st.st_mtime_ns:
                                raise ArchiveError('Source changed while packing: '+rel)
                            stream.write(b'E'+digest)
                            seen[key] = rel
                    files += 1
                    emit(progress,phase='Solid compression',done=done,total=total,current=rel,deduplicated=dedup,zero_bytes=zeros)
                dump(stream,b'Q',dict(total=total,files=files,entries=len(entries)))
            target.flush()
            os.fsync(target.fileno())
        check_cancel(cancel)
        os.link(temp,output)  # atomic publication, never overwrite
        size = output.stat().st_size
        emit(progress,phase='Complete',done=total,total=total)
        return dict(operation='compress',format='AHAS v2 solid XZ',output=str(output),files=files,original_bytes=total,archive_bytes=size,deduplicated=dedup,zero_bytes=zeros,skipped=skipped,
                    warning='This input did not shrink. Already-compressed or very small files can grow; try Media Optimizer for images/video if quality loss is acceptable.' if size>=total else None)
    finally:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass


def restore(archive, output=None, verify=False, max_bytes=1024**4, progress=None, cancel=None):
    archive = Path(archive).expanduser()
    with open(archive,'rb') as f:
        signature = f.read(len(MAGIC))
    if signature.startswith(b'SQLite f'):
        return legacy.restore(archive,output,verify,max_bytes,progress,cancel)
    if signature!=MAGIC:
        raise ArchiveError('Not an AHAS archive (or legacy CLA archive).')
    dest = None
    created = False
    known = {}
    file_meta = {}
    metadata = []
    done = files = records = 0
    zero = bytes(CHUNK)
    try:
        with open(archive,'rb') as raw:
            exact(raw,len(MAGIC))
            stream = XZReader(raw)
            if exact(stream,1)!=b'H':
                raise ArchiveError('Missing AHAS header.')
            header = load(stream)
            total = header.get('total')
            count = header.get('entries')
            if header.get('version')!=2 or not isinstance(total,int) or not 0<=total<=max_bytes or not isinstance(count,int) or not 0<=count<=10000000:
                raise ArchiveError('Invalid header or archive exceeds extraction size limit.')
            if not verify:
                if not output:
                    raise ArchiveError('Choose a new extraction folder.')
                dest = Path(output).expanduser().absolute()
                if not dest.parent.is_dir():
                    raise ArchiveError('Extraction parent does not exist.')
                if total>shutil.disk_usage(dest.parent).free:
                    raise ArchiveError('Not enough free space for restored files.')
                dest.mkdir(mode=0o700,exist_ok=False)
                created = True
            for _ in range(count):
                check_cancel(cancel)
                tag = exact(stream,1)
                if tag not in (b'D',b'F',b'R'):
                    raise ArchiveError('Unexpected AHAS entry type.')
                m = load(stream)
                path = m.get('path')
                safe_name(path)
                key = unicodedata.normalize('NFC',path).casefold()
                size,mode,mtime = m.get('size'),m.get('mode'),m.get('mtime_ns')
                if key in known or not isinstance(size,int) or size<0 or not isinstance(mode,int) or not isinstance(mtime,int):
                    raise ArchiveError('Invalid or conflicting entry metadata.')
                for parent in PurePosixPath(path).parents:
                    if str(parent)=='.':
                        break
                    if known.get(unicodedata.normalize('NFC',str(parent)).casefold())!='dir':
                        raise ArchiveError('Missing parent or unsafe path ordering.')
                known[key] = 'dir' if tag==b'D' else 'file'
                metadata.append((path,mode,mtime,tag==b'D'))
                records += 1
                if tag==b'D':
                    if size!=0:
                        raise ArchiveError('Directory has nonzero size.')
                    if dest:
                        (dest/path).mkdir(mode=0o700)
                    continue
                digest = m.get('digest')
                if not isinstance(digest,str) or len(digest)!=64:
                    raise ArchiveError('Invalid file digest.')
                try:
                    expected = bytes.fromhex(digest)
                except ValueError as exc:
                    raise ArchiveError('Invalid file digest.') from exc
                if done+size>total or done+size>max_bytes:
                    raise ArchiveError('Files exceed declared archive size.')
                if tag==b'R':
                    source = m.get('source')
                    if source not in file_meta or file_meta[source]!=(size,expected):
                        raise ArchiveError('Invalid duplicate reference.')
                    if dest:
                        shutil.copyfile(dest/source,dest/path)
                    done += size
                else:
                    h = hashlib.blake2b(digest_size=32)
                    length = 0
                    f = open(dest/path,'xb') if dest else None
                    try:
                        while True:
                            check_cancel(cancel)
                            part = exact(stream,1)
                            if part==b'E':
                                actual = exact(stream,32)
                                if length!=size or h.digest()!=expected or actual!=expected:
                                    raise ArchiveError('File integrity check failed: '+path)
                                break
                            if part not in (b'B',b'Z'):
                                raise ArchiveError('Invalid data record.')
                            n = struct.unpack('>I',exact(stream,4))[0]
                            if not 0<n<=CHUNK or length+n>size:
                                raise ArchiveError('Invalid or oversized file data.')
                            data = memoryview(zero)[:n] if part==b'Z' else exact(stream,n)
                            h.update(data)
                            length += n
                            done += n
                            if f:
                                if part==b'Z':
                                    f.seek(n,os.SEEK_CUR)
                                else:
                                    f.write(data)
                            emit(progress,phase='Verifying' if verify else 'Extracting',current=path,done=done,total=total)
                        if f:
                            f.truncate()
                    finally:
                        if f:
                            f.close()
                file_meta[path] = (size,expected)
                files += 1
                emit(progress,phase='Verifying' if verify else 'Extracting',current=path,done=done,total=total)
            if exact(stream,1)!=b'Q':
                raise ArchiveError('Missing archive footer.')
            footer = load(stream)
            if footer!=dict(total=total,files=files,entries=records) or done!=total or stream.read(1):
                raise ArchiveError('Archive totals mismatch or trailing payload.')
        check_cancel(cancel)
        if dest:
            # Delay restrictive permissions until all duplicate copies are made.
            for path,mode,mtime,isdir in reversed(metadata):
                os.utime(dest/path,ns=(mtime,mtime))
                os.chmod(dest/path,mode & 0o777)
        created = False
        emit(progress,phase='Complete',done=total,total=total)
        return dict(operation='verify' if verify else 'extract',format='AHAS v2',files=files,original_bytes=total,output=str(dest) if dest else None,verified=True)
    finally:
        if created and dest:
            # All created directories are initially user-writable/private.
            for root,dirs,_ in os.walk(dest):
                os.chmod(root,0o700)
                for d in dirs:
                    os.chmod(Path(root)/d,0o700)
            shutil.rmtree(dest)
