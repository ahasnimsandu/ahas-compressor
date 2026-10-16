import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from contextlib import contextmanager
from compactlocal.archive import compress, restore, ArchiveError, Cancelled, CHUNK_SIZE

@contextmanager
def database(path):
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = self.root/'Source'
        self.src.mkdir()
        self.arc = self.root/'saved.cla'
        self.out = self.root/'Restored'

    def tearDown(self):
        self.tmp.cleanup()

    def make(self):
        (self.src/'empty-folder').mkdir()
        (self.src/'empty.txt').touch()
        (self.src/'hello.txt').write_bytes(b'hello world\n'*10000)
        (self.src/'copy.txt').write_bytes((self.src/'hello.txt').read_bytes())
        (self.src/'café 🌱.bin').write_bytes(os.urandom(6000))
        with open(self.src/'zeros.bin','wb') as f:
            f.truncate(9*1024*1024)

    def test_roundtrip_and_verify(self):
        self.make()
        result = compress([self.src],self.arc)
        self.assertGreater(result['deduplicated'],0)
        self.assertGreater(result['zero_bytes'],0)
        self.assertTrue(restore(self.arc,verify=True)['verified'])
        restore(self.arc,self.out)
        for p in self.src.rglob('*'):
            dest = self.out/'Source'/p.relative_to(self.src)
            if p.is_file():
                self.assertEqual(p.read_bytes(),dest.read_bytes())
                self.assertEqual(p.stat().st_mtime_ns,dest.stat().st_mtime_ns)
            else:
                self.assertTrue(dest.is_dir())

    def test_zero_file_compresses_over_1000x(self):
        with open(self.src/'sparse.bin','wb') as f:
            f.truncate(64*1024*1024)
        result = compress([self.src],self.arc)
        self.assertGreater(result['original_bytes']/result['archive_bytes'],1000)
        restore(self.arc,self.out)
        self.assertEqual((self.out/'Source/sparse.bin').stat().st_size,64*1024*1024)
        self.assertTrue(restore(self.arc,verify=True)['verified'])

    def test_duplicate_chunk(self):
        raw = os.urandom(CHUNK_SIZE)
        (self.src/'a').write_bytes(raw)
        (self.src/'b').write_bytes(raw)
        r = compress([self.src],self.arc,level=0)
        self.assertEqual(r['deduplicated'],CHUNK_SIZE)
        self.assertLess(r['archive_bytes'],2*CHUNK_SIZE)
        restore(self.arc,self.out)
        self.assertEqual((self.out/'Source/b').read_bytes(),raw)

    def test_no_overwrite(self):
        self.make()
        compress([self.src],self.arc)
        before = self.arc.read_bytes()
        with self.assertRaises(ArchiveError):
            compress([self.src],self.arc)
        self.assertEqual(before,self.arc.read_bytes())
        self.out.mkdir()
        (self.out/'keep').write_text('keep')
        with self.assertRaises(FileExistsError):
            restore(self.arc,self.out)
        self.assertEqual((self.out/'keep').read_text(),'keep')

    def test_output_inside_source_rejected(self):
        with self.assertRaises(ArchiveError):
            compress([self.src],self.src/'bad.cla')

    def test_cancellation_cleans_output(self):
        self.make()
        event = threading.Event()
        def progress(**kw):
            if kw.get('done',0)>0:
                event.set()
        with self.assertRaises(Cancelled):
            compress([self.src],self.arc,progress=progress,cancel=event)
        self.assertFalse(self.arc.exists())
        self.assertFalse(list(self.root.glob('.compactlocal-*')))

    def test_cancel_extract_cleans_output(self):
        self.make()
        compress([self.src],self.arc)
        event = threading.Event()
        def progress(**kw):
            event.set()
        with self.assertRaises(Cancelled):
            restore(self.arc,self.out,progress=progress,cancel=event)
        self.assertFalse(self.out.exists())

    def test_corrupt_checksum_rejected_and_cleaned(self):
        self.make()
        compress([self.src],self.arc)
        with database(self.arc) as db:
            db.execute("UPDATE chunks SET digest=zeroblob(32) WHERE id=(SELECT min(id) FROM chunks)")
        with self.assertRaises(ArchiveError):
            restore(self.arc,self.out)
        self.assertFalse(self.out.exists())

    def test_path_traversal_rejected(self):
        self.make()
        compress([self.src],self.arc)
        with database(self.arc) as db:
            db.execute("UPDATE entries SET path='../escape' WHERE path='Source/empty.txt'")
        with self.assertRaises(ArchiveError):
            restore(self.arc,self.out)
        self.assertFalse((self.root/'escape').exists())
        self.assertFalse(self.out.exists())

    def test_expansion_limit(self):
        self.make()
        compress([self.src],self.arc)
        with self.assertRaises(ArchiveError):
            restore(self.arc,self.out,max_bytes=1024)
        self.assertFalse(self.out.exists())

    def test_symlink_skipped(self):
        (self.src/'file').write_text('data')
        (self.src/'link').symlink_to('file')
        result = compress([self.src],self.arc)
        self.assertEqual(len(result['skipped']),1)
        restore(self.arc,self.out)
        self.assertFalse((self.out/'Source/link').exists())

    def test_bad_format(self):
        self.arc.write_bytes(b'not an archive')
        with self.assertRaises((sqlite3.DatabaseError,ArchiveError)):
            restore(self.arc,verify=True)

    def test_source_mutation_rejected(self):
        (self.src/'a').write_bytes(b'a'*100)
        def progress(**kw):
            if kw.get('current')=='Source/a':
                (self.src/'a').write_bytes(b'b'*200)
        with self.assertRaises(ArchiveError):
            compress([self.src],self.arc,progress=progress)
        self.assertFalse(self.arc.exists())

    def test_empty_directory(self):
        compress([self.src],self.arc)
        restore(self.arc,self.out)
        self.assertTrue((self.out/'Source').is_dir())
        self.assertTrue(restore(self.arc,verify=True)['verified'])

    def test_missing_parent_rejected(self):
        self.make()
        compress([self.src],self.arc)
        with database(self.arc) as db:
            db.execute("DELETE FROM entries WHERE path='Source'")
        with self.assertRaises(ArchiveError):
            restore(self.arc,self.out)

    def test_oversized_span_rejected(self):
        self.make()
        compress([self.src],self.arc)
        with database(self.arc) as db:
            db.execute('UPDATE spans SET size=20000000 WHERE entry_id=(SELECT min(entry_id) FROM spans)')
        with self.assertRaises(ArchiveError):
            restore(self.arc,self.out)
        self.assertFalse(self.out.exists())

    def test_incomplete_rejected(self):
        self.make()
        compress([self.src],self.arc)
        with database(self.arc) as db:
            db.execute("DELETE FROM metadata WHERE key='complete'")
        with self.assertRaises(ArchiveError):
            restore(self.arc,verify=True)

    def test_normalized_case_collision(self):
        (self.src/'abc').write_text('a')
        # The host may itself have a case-insensitive filesystem.
        if not (self.src/'ABC').exists():
            (self.src/'ABC').write_text('b')
            with self.assertRaises(ArchiveError):
                compress([self.src],self.arc)

if __name__ == '__main__':
    unittest.main()
