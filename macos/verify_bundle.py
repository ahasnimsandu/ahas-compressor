"""Platform-independent structural checks, NOT Apple's codesign/Gatekeeper validation.
Run: python3 verify_bundle.py /path/to/AHAS.app
Checks resource hashes, link targets, arm64 Mach-O page hashes, and main bundle seals.
"""
from pathlib import Path
import hashlib
import os
import plistlib
import struct
import sys


def macho(path):
    data = path.read_bytes()
    if data[:4] != b'\xcf\xfa\xed\xfe':
        return False
    header = struct.unpack_from('<8I',data)
    if header[1] != 0x100000c:
        raise ValueError('Expected arm64: '+str(path))
    offset = 32
    signature = None
    for _ in range(header[4]):
        cmd, length = struct.unpack_from('<II',data,offset)
        if cmd == 0x1d:
            pos,size = struct.unpack_from('<II',data,offset+8)
            signature = data[pos:pos+size]
        offset += length
    assert signature, ('No signature',path)
    magic,length,count = struct.unpack_from('>III',signature)
    assert magic == 0xfade0cc0
    directories=[]
    for i in range(count):
        slot,pos=struct.unpack_from('>II',signature,12+i*8)
        m,n=struct.unpack_from('>II',signature,pos)
        if m==0xfade0c02:
            cd=signature[pos:pos+n]
            _,_,version,flags,hashoff,ident,special,slots,limit=struct.unpack_from('>9I',cd)
            hsize,htype,platform,page=struct.unpack_from('>4B',cd,36)
            hashfn = hashlib.sha256 if htype in (2,3) else hashlib.sha1 if htype==1 else None
            assert hashfn, ('Unsupported signature hash',htype)
            page_bytes=1<<page
            assert slots==(limit+page_bytes-1)//page_bytes
            for j in range(slots):
                actual=hashfn(data[j*page_bytes:min(limit,(j+1)*page_bytes)]).digest()[:hsize]
                assert actual==cd[hashoff+j*hsize:hashoff+(j+1)*hsize], ('Page signature mismatch',path,j)
            directories.append((cd,hashoff,hsize,hashfn,special))
    assert directories
    if path.parent.name=='MacOS':
        contents=path.parent.parent
        for cd,hashoff,hsize,hashfn,special in directories:
            for slot,resource in [(1,contents/'Info.plist'),(3,contents/'_CodeSignature/CodeResources')]:
                assert special>=slot
                assert hashfn(resource.read_bytes()).digest()[:hsize]==cd[hashoff-slot*hsize:hashoff-(slot-1)*hsize],('Bundle special seal mismatch',resource)
    return True


def main(bundle):
    contents=Path(bundle)/'Contents'
    info=plistlib.loads((contents/'Info.plist').read_bytes())
    assert info['CFBundleExecutable']=='AHAS'
    assert info['NSHumanReadableCopyright']=='Made by Ahas Nimsandu'
    envelope=plistlib.loads((contents/'_CodeSignature/CodeResources').read_bytes())
    files=links=machos=0
    for rel,seal in envelope['files2'].items():
        path=contents/rel
        if 'symlink' in seal:
            assert path.is_symlink() and os.readlink(path)==seal['symlink'],path
            links+=1
        else:
            if 'hash2' in seal:
                assert hashlib.sha256(path.read_bytes()).digest()==seal['hash2'],path
            if 'hash' in seal:
                assert hashlib.sha1(path.read_bytes()).digest()==seal['hash'],path
            files+=1
    for path in contents.rglob('*'):
        if path.is_file() and not path.is_symlink():
            if path.open('rb').read(4)==b'\xcf\xfa\xed\xfe':
                machos += int(macho(path))
    print(f'PASS: {files} sealed resource files, {links} sealed symlinks, {machos} arm64 Mach-O signatures (page hashes), Info.plist and CodeResources seals.')
    print('This is structural integrity testing, not Developer ID trust, notarization, or an Apple codesign/Gatekeeper assessment.')

if __name__=='__main__':
    main(sys.argv[1])
