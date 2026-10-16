from contextlib import ExitStack
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from compactlocal import media


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.src=self.root/'Photo.png';self.src.write_bytes(b'o'*1000)
        self.out=self.root/'Optimized'

    def tearDown(self):self.temp.cleanup()

    def platform(self):
        stack=ExitStack();stack.enter_context(patch.object(media.sys,'platform','darwin'))
        original=Path.is_file
        stack.enter_context(patch.object(Path,'is_file',lambda p:True if str(p) in ('/usr/bin/sips','/usr/bin/avconvert') else original(p)))
        return stack

    def fake(self,size):
        def run(command,cancel,progress,current):
            index=command.index('--out') if '--out' in command else command.index('--output')
            Path(command[index+1]).write_bytes(b'x'*size)
        return run

    def test_smaller_copy_original_unchanged(self):
        with self.platform(),patch.object(media,'execute',self.fake(100)):
            r=media.optimize([self.src],self.out)
        self.assertEqual(r['saved_bytes'],900);self.assertEqual(r['optimized'],1)
        self.assertEqual(self.src.read_bytes(),b'o'*1000)
        self.assertEqual((self.out/'Photo-optimized.jpg').read_bytes(),b'x'*100)

    def test_growing_conversion_is_discarded(self):
        with self.platform(),patch.object(media,'execute',self.fake(2000)):
            r=media.optimize([self.src],self.out)
        self.assertEqual(r['kept_original'],1);self.assertEqual(r['saved_bytes'],0)
        self.assertEqual((self.out/'Photo.png').read_bytes(),self.src.read_bytes())

    def test_failed_conversion_keeps_original(self):
        with self.platform(),patch.object(media,'execute',side_effect=media.ArchiveError('Unsupported codec')):
            r=media.optimize([self.src],self.out)
        self.assertEqual(r['kept_original'],1);self.assertIn('Unsupported',r['items'][0]['error'])
        self.assertEqual((self.out/'Photo.png').read_bytes(),self.src.read_bytes())

    def test_cancel_removes_output(self):
        with self.platform(),patch.object(media,'execute',side_effect=media.Cancelled('cancel')):
            with self.assertRaises(media.Cancelled):media.optimize([self.src],self.out)
        self.assertFalse(self.out.exists())

    def test_no_overwrite(self):
        self.out.mkdir()
        with self.platform():
            with self.assertRaises(media.ArchiveError):media.optimize([self.src],self.out)
        self.assertTrue(self.out.exists())

    def test_nested_output(self):
        src=self.root/'Sources';src.mkdir();(src/'a.jpg').write_bytes(b'a'*100)
        with self.platform():
            with self.assertRaises(media.ArchiveError):media.optimize([src],src/'Optimized')

    def test_unsupported_media(self):
        p=self.root/'audio.mp3';p.write_bytes(b'a')
        with self.platform():
            with self.assertRaises(media.ArchiveError):media.optimize([p],self.out)

    def test_non_macos_error(self):
        with patch.object(media.sys,'platform','linux'):
            with self.assertRaisesRegex(media.ArchiveError,'macOS'):media.optimize([self.src],self.out)

    def test_video_arguments_and_profile(self):
        src=self.root/'movie.mp4';src.write_bytes(b'v'*1000)
        with self.platform(),patch.object(media,'execute',self.fake(100)) as _,patch.object(media,'video_preset',return_value='Preset1280x720') as preset:
            r=media.optimize([src],self.out)
        preset.assert_called_once_with('balanced');self.assertEqual(r['optimized'],1)
        self.assertTrue((self.out/'movie-optimized.mov').exists())

    def test_name_collisions_do_not_overwrite(self):
        p=self.root/'Photo.jpg';p.write_bytes(b'q'*1000)
        with self.platform(),patch.object(media,'execute',self.fake(100)):
            r=media.optimize([self.src,p],self.out)
        self.assertEqual(r['optimized'],2);self.assertEqual(len(list(self.out.iterdir())),2)

    @unittest.skipUnless(sys.platform=='darwin','Real macOS system-tool test')
    def test_real_sips_compression(self):
        # Standard-library generated uncompressed 24-bit BMP; no Pillow dependency.
        w=h=512;row=bytes([10,50,150])*w;pixels=row*h
        header=b'BM'+struct.pack('<IHHI',54+len(pixels),0,0,54)+struct.pack('<IIIHHIIIIII',40,w,h,1,24,0,len(pixels),2835,2835,0,0)
        p=self.root/'fixture.bmp';p.write_bytes(header+pixels);before=p.read_bytes()
        r=media.optimize([p],self.out)
        self.assertEqual(r['optimized'],1)
        dest=self.out/'fixture-optimized.jpg'
        self.assertTrue(dest.read_bytes().startswith(b'\xff\xd8'))
        self.assertLess(dest.stat().st_size,p.stat().st_size)
        self.assertEqual(before,p.read_bytes())

    @unittest.skipUnless(sys.platform=='darwin','Real macOS preset enumeration')
    def test_real_video_preset_available(self):
        self.assertTrue(media.video_preset('balanced').startswith('Preset'))
