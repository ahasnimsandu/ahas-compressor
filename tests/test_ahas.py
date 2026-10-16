import hashlib
import json
import lzma
import os
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from compactlocal import ahas
from compactlocal import archive as legacy


class AhasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.src = self.root/'Source'
        self.src.mkdir()
        self.arc = self.root/'data.ahas'
        self.out = self.root/'Restored'

    def tearDown(self):
        self.temp.cleanup()

    def create(self):
        (self.src/'Empty').mkdir()
        (self.src/'empty.txt').touch()
        (self.src/'text.txt').write_bytes(b'AHAS solid compression test\n'*100000)
        (self.src/'copy.txt').write_bytes((self.src/'text.txt').read_bytes())
        (self.src/'café 🌱.bin').write_bytes(os.urandom(8000))
        with (self.src/'zeros').open('wb') as f:f.truncate(9*1024**2)

    def rewrite(self, payload):
        self.arc.write_bytes(ahas.MAGIC+lzma.compress(payload))

    def payload(self):
        return lzma.decompress(self.arc.read_bytes()[len(ahas.MAGIC):])

    def test_roundtrip(self):
        self.create()
        r = ahas.compress([self.src],self.arc)
        self.assertGreater(r['deduplicated'],0)
        self.assertGreater(r['zero_bytes'],0)
        ahas.restore(self.arc,self.out)
        for p in self.src.rglob('*'):
            dest = self.out/'Source'/p.relative_to(self.src)
            if p.is_file():
                self.assertEqual(p.read_bytes(),dest.read_bytes())
                self.assertEqual(p.stat().st_mtime_ns,dest.stat().st_mtime_ns)
            else:self.assertTrue(dest.is_dir())
        self.assertTrue(ahas.restore(self.arc,verify=True)['verified'])

    def test_lower_overhead_than_legacy(self):
        (self.src/'text').write_bytes(b'abc def ghi\n'*100000)
        old = legacy.compress([self.src],self.root/'old.cla')
        new = ahas.compress([self.src],self.arc)
        self.assertLess(new['archive_bytes'],old['archive_bytes']/5)

    def test_zero_ratio(self):
        with (self.src/'zeros').open('wb') as f:f.truncate(64*1024**2)
        r = ahas.compress([self.src],self.arc)
        self.assertGreater(r['original_bytes']/r['archive_bytes'],10000)
        self.assertTrue(ahas.restore(self.arc,verify=True)['verified'])

    def test_extension(self):
        r = ahas.compress([self.src],self.root/'no-extension')
        self.assertTrue(r['output'].endswith('.ahas'))
        self.assertTrue(Path(r['output']).exists())

    def test_random_growth_reported(self):
        (self.src/'r').write_bytes(os.urandom(10000))
        r = ahas.compress([self.src],self.arc)
        self.assertIsNotNone(r['warning'])
        ahas.restore(self.arc,self.out)

    def test_empty_folder(self):
        ahas.compress([self.src],self.arc)
        ahas.restore(self.arc,self.out)
        self.assertTrue((self.out/'Source').is_dir())

    def test_empty_file_duplicates(self):
        (self.src/'a').touch();(self.src/'b').touch()
        ahas.compress([self.src],self.arc)
        ahas.restore(self.arc,self.out)
        self.assertEqual((self.out/'Source/b').read_bytes(),b'')

    def test_legacy_read(self):
        self.create()
        p=self.root/'old.cla'
        legacy.compress([self.src],p)
        self.assertTrue(ahas.restore(p,verify=True)['verified'])
        ahas.restore(p,self.out)

    def test_truncated(self):
        self.create();ahas.compress([self.src],self.arc)
        self.arc.write_bytes(self.arc.read_bytes()[:-20])
        with self.assertRaises((ahas.ArchiveError,lzma.LZMAError)):
            ahas.restore(self.arc,self.out)
        self.assertFalse(self.out.exists())

    def test_trailing_stream_data(self):
        ahas.compress([self.src],self.arc)
        with self.arc.open('ab') as f:f.write(b'junk')
        with self.assertRaises(ahas.ArchiveError):ahas.restore(self.arc,verify=True)

    def test_bit_corruption(self):
        self.create();ahas.compress([self.src],self.arc)
        b=bytearray(self.arc.read_bytes());b[len(b)//2]^=1;self.arc.write_bytes(b)
        with self.assertRaises((ahas.ArchiveError,lzma.LZMAError,ValueError)):
            ahas.restore(self.arc,self.out)
        self.assertFalse(self.out.exists())

    def test_unsafe_paths(self):
        ahas.compress([self.src],self.arc)
        self.rewrite(self.payload().replace(b'"path":"Source"',b'"path":"../bad"'))
        # Different string lengths also invalidate the record length, which is rejected.
        with self.assertRaises((ahas.ArchiveError,ValueError,json.JSONDecodeError)):
            ahas.restore(self.arc,self.out)
        self.assertFalse((self.root/'bad').exists())

    def test_expansion_limit(self):
        self.create();ahas.compress([self.src],self.arc)
        with self.assertRaises(ahas.ArchiveError):ahas.restore(self.arc,self.out,max_bytes=1024)
        self.assertFalse(self.out.exists())

    def test_cancel_compress(self):
        self.create();event=threading.Event()
        def progress(**kw):
            if kw.get('phase')=='Solid compression':event.set()
        with self.assertRaises(ahas.Cancelled):ahas.compress([self.src],self.arc,progress=progress,cancel=event)
        self.assertFalse(self.arc.exists());self.assertFalse(list(self.root.glob('.ahas-*')))

    def test_cancel_restore(self):
        self.create();ahas.compress([self.src],self.arc);event=threading.Event()
        def progress(**kw):event.set()
        with self.assertRaises(ahas.Cancelled):ahas.restore(self.arc,self.out,progress=progress,cancel=event)
        self.assertFalse(self.out.exists())

    def test_no_overwrite(self):
        ahas.compress([self.src],self.arc)
        original=self.arc.read_bytes()
        with self.assertRaises(ahas.ArchiveError):ahas.compress([self.src],self.arc)
        self.assertEqual(original,self.arc.read_bytes())
        self.out.mkdir()
        with self.assertRaises(FileExistsError):ahas.restore(self.arc,self.out)
        self.assertTrue(self.out.exists())

    def test_nested_output_rejected(self):
        with self.assertRaises(ahas.ArchiveError):ahas.compress([self.src],self.src/'out.ahas')

    def test_source_mutation(self):
        (self.src/'a').write_text('a'*100)
        def progress(**kw):
            if kw.get('phase')=='Fingerprinting for duplicates' and kw.get('done',0)>0:
                (self.src/'a').write_text('b'*200)
        with self.assertRaises(ahas.ArchiveError):ahas.compress([self.src],self.arc,progress=progress)
        self.assertFalse(self.arc.exists())

    def test_exact_file_deduplication(self):
        block=os.urandom(200000)
        (self.src/'a').write_bytes(block)
        (self.src/'b').write_bytes(block)
        r=ahas.compress([self.src],self.arc,level=1)
        self.assertEqual(r['deduplicated'],len(block))
        ahas.restore(self.arc,self.out)
        self.assertEqual((self.out/'Source/b').read_bytes(),block)

    def test_invalid_level(self):
        with self.assertRaises(ahas.ArchiveError):ahas.compress([self.src],self.arc,level=0)

    def crafted(self,tag,meta,payload=b'',total=0):
        import io
        stream=io.BytesIO();ahas.dump(stream,b'H',dict(version=2,total=total,entries=1));ahas.dump(stream,tag,meta);stream.write(payload);ahas.dump(stream,b'Q',dict(total=total,files=0 if tag==b'D' else 1,entries=1));self.rewrite(stream.getvalue())

    def test_crafted_traversal(self):
        self.crafted(b'D',dict(path='../escape',size=0,mode=0o755,mtime_ns=1))
        with self.assertRaises(ahas.ArchiveError):ahas.restore(self.arc,self.out)
        self.assertFalse(self.out.exists());self.assertFalse((self.root/'escape').exists())

    def test_crafted_invalid_duplicate(self):
        digest=hashlib.blake2b(b'',digest_size=32).hexdigest()
        self.crafted(b'R',dict(path='a',size=0,mode=0o644,mtime_ns=1,digest=digest,source='missing'))
        with self.assertRaises(ahas.ArchiveError):ahas.restore(self.arc,self.out)
        self.assertFalse(self.out.exists())

    def test_crafted_hash_mismatch(self):
        digest=hashlib.blake2b(b'a',digest_size=32).digest()
        data=b'B'+struct.pack('>I',1)+b'b'+b'E'+digest
        self.crafted(b'F',dict(path='a',size=1,mode=0o644,mtime_ns=1,digest=digest.hex()),data,total=1)
        with self.assertRaises(ahas.ArchiveError):ahas.restore(self.arc,self.out)
        self.assertFalse(self.out.exists())

    def test_crafted_oversized_data_record(self):
        digest=hashlib.blake2b(b'a',digest_size=32).hexdigest()
        self.crafted(b'F',dict(path='a',size=1,mode=0o644,mtime_ns=1,digest=digest),b'B'+struct.pack('>I',20000000),total=1)
        with self.assertRaises(ahas.ArchiveError):ahas.restore(self.arc,self.out)
        self.assertFalse(self.out.exists())

    def test_oversized_json(self):
        self.rewrite(b'H'+struct.pack('>I',ahas.JSON_LIMIT+1))
        with self.assertRaises(ahas.ArchiveError):ahas.restore(self.arc,verify=True)
