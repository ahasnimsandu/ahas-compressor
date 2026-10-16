"""CompactLocal v1: streaming, lossless, deduplicating SQLite archives.
No third-party dependencies. Archive format is intentionally documented in README.
"""
from __future__ import annotations
import hashlib
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import tempfile
import threading
import time
import unicodedata

VERSION = 1
APP_ID = 0x434C4131
CHUNK_SIZE = 4 * 1024 * 1024
MAX_CHUNK = 16 * 1024 * 1024

class Cancelled(Exception):
    pass

class ArchiveError(Exception):
    pass


def check_cancel(cancel):
    if cancel and cancel.is_set():
        raise Cancelled('Operation cancelled; incomplete output removed.')


def emit(progress, **values):
    if progress:
        progress(**values)


def safe_name(name):
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise ArchiveError('Invalid archive path')
    p = PurePosixPath(name)
    if p.is_absolute() or any(x in ('', '.', '..') for x in name.split('/')):
        raise ArchiveError('Unsafe archive path: ' + name)
    return p


def connect_read(path):
    uri = Path(path).absolute().as_uri() + '?mode=ro'
    db = sqlite3.connect(uri, uri=True)
    db.execute('PRAGMA trusted_schema=OFF')
    db.execute('PRAGMA query_only=ON')
    db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 2 * MAX_CHUNK + 65536)
    try:
        if db.execute('PRAGMA application_id').fetchone()[0] != APP_ID:
            raise ArchiveError('Not a CompactLocal archive.')
        meta = dict(db.execute('SELECT key,value FROM metadata'))
        if meta.get('version') != str(VERSION):
            raise ArchiveError('Unsupported archive version.')
        return db
    except BaseException:
        db.close()
        raise


def scan(inputs, cancel=None):
    entries, skipped, names = [], [], set()
    def visit(path, relative):
        check_cancel(cancel)
        safe_name(relative)
        key = unicodedata.normalize('NFC', relative).casefold()
        if key in names:
            raise ArchiveError('Duplicate or case-conflicting path: ' + relative)
        names.add(key)
        st = path.lstat()
        if stat.S_ISLNK(st.st_mode):
            skipped.append(str(path) + ' (symbolic link)')
        elif stat.S_ISDIR(st.st_mode):
            entries.append((path, relative, 'dir', st))
            for child in sorted(path.iterdir(), key=lambda x: x.name):
                visit(child, relative + '/' + child.name)
        elif stat.S_ISREG(st.st_mode):
            entries.append((path, relative, 'file', st))
        else:
            skipped.append(str(path) + ' (special file)')
    for source in inputs:
        path = Path(source).expanduser().absolute()
        visit(path, path.name)
    if not entries:
        raise ArchiveError('No regular files or directories selected.')
    return entries, skipped


def compress(inputs, output, level=3, progress=None, cancel=None):
    if not inputs:
        raise ArchiveError('Choose at least one input.')
    if level not in (0, 3, 6):
        raise ArchiveError('Compression level must be 0, 3, or 6.')
    output = Path(output).expanduser().absolute()
    # A source tree must not contain the output (including via an aliased parent).
    actual_output = output.resolve()
    for source in inputs:
        src = Path(source).expanduser().resolve()
        if actual_output == src or (src.is_dir() and actual_output.is_relative_to(src)):
            raise ArchiveError('Save the archive outside all selected source folders.')
    if output.exists():
        raise ArchiveError('Output already exists. Choose a new archive name.')
    if not output.parent.is_dir():
        raise ArchiveError('Output parent folder does not exist.')
    emit(progress, phase='Scanning', current='')
    entries, skipped = scan(inputs, cancel)
    total = sum(st.st_size for _, _, kind, st in entries if kind == 'file')
    fd, temp = tempfile.mkstemp(prefix='.compactlocal-', suffix='.partial', dir=output.parent)
    os.close(fd)
    db = None
    done = unique = dedup = zeros = files = 0
    try:
        db = sqlite3.connect(temp)
        db.executescript('''PRAGMA journal_mode=DELETE;
        PRAGMA synchronous=FULL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE entries(id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL,
          kind TEXT NOT NULL, size INTEGER NOT NULL, mode INTEGER NOT NULL,
          mtime_ns INTEGER NOT NULL, digest BLOB);
        CREATE TABLE chunks(id INTEGER PRIMARY KEY, digest BLOB UNIQUE NOT NULL,
          raw_size INTEGER NOT NULL, codec TEXT NOT NULL, data BLOB NOT NULL);
        CREATE TABLE spans(entry_id INTEGER NOT NULL REFERENCES entries(id),
          seq INTEGER NOT NULL, chunk_id INTEGER REFERENCES chunks(id), size INTEGER NOT NULL,
          PRIMARY KEY(entry_id,seq));''')
        db.execute('PRAGMA application_id=' + str(APP_ID))
        db.executemany('INSERT INTO metadata VALUES (?,?)', [('version',str(VERSION)), ('chunk_size',str(CHUNK_SIZE)), ('created',str(int(time.time())))])
        for path, rel, kind, st in entries:
            check_cancel(cancel)
            size = st.st_size if kind == 'file' else 0
            eid = db.execute('INSERT INTO entries(path,kind,size,mode,mtime_ns) VALUES (?,?,?,?,?)',
                             (rel,kind,size,stat.S_IMODE(st.st_mode),st.st_mtime_ns)).lastrowid
            emit(progress, phase='Compressing', current=rel, total=total, done=done, skipped=len(skipped))
            if kind == 'dir':
                continue
            flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
            f = os.fdopen(os.open(path, flags), 'rb')
            with f:
                before = os.fstat(f.fileno())
                if not stat.S_ISREG(before.st_mode) or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns) != (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns):
                    raise ArchiveError('Source changed during scanning: ' + rel)
                digest = hashlib.blake2b(digest_size=32)
                read_size = 0
                seq = 0
                while True:
                    check_cancel(cancel)
                    raw = f.read(CHUNK_SIZE)
                    if not raw:
                        break
                    read_size += len(raw)
                    if read_size > size:
                        raise ArchiveError('Source grew during compression: ' + rel)
                    digest.update(raw)
                    cid = None
                    if not raw.strip(b'\x00'):
                        zeros += len(raw)
                    else:
                        h = hashlib.blake2b(raw, digest_size=32).digest()
                        row = db.execute('SELECT id FROM chunks WHERE digest=?', (h,)).fetchone()
                        if row:
                            cid = row[0]
                            dedup += len(raw)
                        else:
                            encoded = lzma.compress(raw, preset=level)
                            codec = 'xz'
                            if len(encoded) >= len(raw):
                                encoded, codec = raw, 'raw'
                            cid = db.execute('INSERT INTO chunks(digest,raw_size,codec,data) VALUES (?,?,?,?)', (h,len(raw),codec,encoded)).lastrowid
                            unique += len(raw)
                    db.execute('INSERT INTO spans VALUES (?,?,?,?)', (eid,seq,cid,len(raw)))
                    done += len(raw)
                    seq += 1
                    emit(progress, phase='Compressing', current=rel, total=total, done=done,
                         deduplicated=dedup, zero_bytes=zeros, archive_bytes=os.path.getsize(temp))
                    if seq % 16 == 0:
                        db.commit()
                after = os.fstat(f.fileno())
                if read_size != size or after.st_mtime_ns != before.st_mtime_ns or after.st_size != before.st_size:
                    raise ArchiveError('Source changed during compression: ' + rel)
                db.execute('UPDATE entries SET digest=? WHERE id=?', (digest.digest(),eid))
                files += 1
            db.commit()
        db.execute('INSERT INTO metadata VALUES (?,?)', ('complete','yes'))
        db.commit()
        db.close()
        db = None
        check_cancel(cancel)
        # Hard-link publication never overwrites an existing destination.
        os.link(temp, output)
        os.unlink(temp)
        result = dict(operation='compress', output=str(output), original_bytes=total,
                      archive_bytes=output.stat().st_size, files=files, deduplicated=dedup,
                      zero_bytes=zeros, skipped=skipped)
        emit(progress, phase='Complete', done=total, total=total)
        return result
    finally:
        if db is not None:
            db.close()
        for suffix in ('', '-journal'):
            try:
                os.unlink(temp + suffix)
            except FileNotFoundError:
                pass


def manifest(db, max_bytes):
    if dict(db.execute('SELECT key,value FROM metadata')).get('complete') != 'yes':
        raise ArchiveError('Archive is incomplete.')
    rows = db.execute('SELECT id,path,kind,size,mode,mtime_ns,digest FROM entries ORDER BY id').fetchall()
    paths = {}
    total = 0
    for eid, path, kind, size, mode, mtime, digest in rows:
        safe_name(path)
        key = unicodedata.normalize('NFC', path).casefold()
        if key in paths or kind not in ('dir','file') or not isinstance(size,int) or size < 0:
            raise ArchiveError('Invalid or conflicting archive entry.')
        if not isinstance(mode,int) or not isinstance(mtime,int):
            raise ArchiveError('Invalid file metadata.')
        if kind == 'file' and (not isinstance(digest,bytes) or len(digest) != 32):
            raise ArchiveError('Invalid file checksum.')
        if kind == 'dir' and size != 0:
            raise ArchiveError('Invalid directory size.')
        paths[key] = kind
        total += size
        if total > max_bytes:
            raise ArchiveError('Archive exceeds the selected extraction size limit.')
    for _, path, *_ in rows:
        for parent in PurePosixPath(path).parents:
            if str(parent) == '.':
                break
            key = unicodedata.normalize('NFC',str(parent)).casefold()
            if paths.get(key) != 'dir':
                raise ArchiveError('Missing or invalid parent directory.')
    return rows, total


def decode_chunk(db, cid, expected):
    row = db.execute('SELECT digest,raw_size,codec,data FROM chunks WHERE id=?', (cid,)).fetchone()
    if not row:
        raise ArchiveError('Missing data chunk.')
    digest, size, codec, data = row
    if size != expected or not 0 < size <= MAX_CHUNK or not isinstance(data,bytes) or len(data) > MAX_CHUNK:
        raise ArchiveError('Invalid chunk size.')
    if codec == 'raw':
        raw = data
    elif codec == 'xz':
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=256 * 1024 * 1024)
        raw = decoder.decompress(data, max_length=size+1)
        if not decoder.eof or decoder.unused_data:
            raise ArchiveError('Invalid or oversized compressed chunk.')
    else:
        raise ArchiveError('Unknown chunk encoding.')
    if len(raw) != size or hashlib.blake2b(raw,digest_size=32).digest() != digest:
        raise ArchiveError('Chunk checksum mismatch; archive may be damaged.')
    return raw


def restore(archive, output=None, verify=False, max_bytes=1024**4, progress=None, cancel=None):
    db = connect_read(Path(archive).expanduser())
    created = False
    dest = None
    try:
        rows, total = manifest(db, max_bytes)
        if not verify:
            if not output:
                raise ArchiveError('Choose a new extraction folder.')
            dest = Path(output).expanduser().absolute()
            if not dest.parent.is_dir():
                raise ArchiveError('Extraction parent does not exist.')
            if total > shutil.disk_usage(dest.parent).free:
                raise ArchiveError('Not enough free disk space for the full uncompressed size.')
            dest.mkdir(mode=0o700, exist_ok=False)
            created = True
            for _, path, kind, *_ in sorted(rows, key=lambda r: len(PurePosixPath(r[1]).parts)):
                if kind == 'dir':
                    (dest / path).mkdir(mode=0o700)
        done = files = 0
        zero = bytes(MAX_CHUNK)
        for eid, path, kind, size, mode, mtime, digest in rows:
            check_cancel(cancel)
            if kind == 'dir':
                continue
            h = hashlib.blake2b(digest_size=32)
            count = 0
            f = None if verify else open(dest / path, 'xb')
            try:
                for seq, cid, length in db.execute('SELECT seq,chunk_id,size FROM spans WHERE entry_id=? ORDER BY seq', (eid,)):
                    check_cancel(cancel)
                    if seq != count or not isinstance(length,int) or not 0 < length <= MAX_CHUNK or done < 0:
                        raise ArchiveError('Invalid file span.')
                    if length > size:
                        raise ArchiveError('File span exceeds declared size.')
                    raw = memoryview(zero)[:length] if cid is None else decode_chunk(db,cid,length)
                    size -= length
                    h.update(raw)
                    if f:
                        if cid is None:
                            f.seek(length, os.SEEK_CUR)
                        else:
                            f.write(raw)
                    done += length
                    count += 1
                    emit(progress, phase='Verifying' if verify else 'Extracting', current=path, done=done, total=total)
                if size != 0 or h.digest() != digest:
                    raise ArchiveError('File checksum or length mismatch: ' + path)
                if f:
                    f.truncate()
            finally:
                if f:
                    f.close()
            if not verify:
                os.chmod(dest/path, mode & 0o777)
                os.utime(dest/path, ns=(mtime,mtime))
            files += 1
        if not verify:
            for _, path, kind, _, mode, mtime, _ in reversed(sorted(rows,key=lambda r: len(PurePosixPath(r[1]).parts))):
                if kind == 'dir':
                    os.utime(dest/path, ns=(mtime,mtime))
                    os.chmod(dest/path, mode & 0o777)
        check_cancel(cancel)
        created = False
        emit(progress, phase='Complete', done=total,total=total)
        return dict(operation='verify' if verify else 'extract', files=files, original_bytes=total, output=str(dest) if dest else None, verified=True)
    finally:
        db.close()
        if created and dest:
            def fix_permissions(func, path, exc):
                os.chmod(path,0o700)
                func(path)
            shutil.rmtree(dest, onerror=fix_permissions)
