"""Linux build helper for the macOS arm64 package.
Expects mac-build work directory containing upstream python/ and compiled launcher.
Build-time-only Pillow and ds_store modules; neither is needed by the Mac app.
"""
from pathlib import Path
import json
import os
import plistlib
import shutil
import struct
import re
import sys
from PIL import Image, ImageDraw

SOURCE = Path(__file__).resolve().parent.parent
APP_VERSION = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", (SOURCE/'compactlocal/__init__.py').read_text()).group(1)
WORK = Path(sys.argv[1]).resolve()
STAGE = WORK/'stage'
if STAGE.exists():
    shutil.rmtree(STAGE)
RES = STAGE/'AHAS.app/Contents/Resources'
MAC = STAGE/'AHAS.app/Contents/MacOS'
RES.mkdir(parents=True)
MAC.mkdir()
shutil.copy2(WORK/'AHAS-launcher', MAC/'AHAS')
os.chmod(MAC/'AHAS',0o755)
shutil.copytree(WORK/'python',RES/'python',symlinks=True)
shutil.copytree(SOURCE/'compactlocal',RES/'app/compactlocal',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copytree(SOURCE/'macos/runtime-licenses',RES/'licenses/runtime')
for name in ('native_host.py','launch.sh','RUNTIME-PROVENANCE.json'):
    shutil.copy2(SOURCE/'macos'/name,RES/name)
os.chmod(RES/'launch.sh',0o755)
shutil.copy2(SOURCE/'LICENSE',RES/'licenses/AHAS-MIT.txt')
shutil.copy2(SOURCE/'macos/READ ME FIRST.txt',STAGE/'READ ME FIRST.txt')
shutil.copy2(SOURCE/'macos/READ ME FIRST.txt',RES/'READ ME FIRST.txt')
shutil.copy2(SOURCE/'README.md',RES/'ENGINE-AND-PORTABLE-EDITION.md')
shutil.copy2(SOURCE/'VALIDATION.md',RES/'ENGINE-VALIDATION.md')
info = {
 'CFBundleDevelopmentRegion':'en', 'CFBundleDisplayName':'AHAS',
 'CFBundleName':'AHAS', 'CFBundleExecutable':'AHAS',
 'CFBundleIdentifier':'app.ahasnimsandu.ahas', 'CFBundlePackageType':'APPL',
 'CFBundleShortVersionString':APP_VERSION, 'CFBundleVersion':APP_VERSION,
 'CFBundleIconFile':'AHAS.icns', 'LSMinimumSystemVersion':'11.0',
 'LSArchitecturePriority':['arm64'], 'LSRequiresNativeExecution':True,
 'NSHighResolutionCapable':True, 'NSPrincipalClass':'NSApplication',
 'NSHumanReadableCopyright':'Made by Ahas Nimsandu',
 'NSAppTransportSecurity':{'NSAllowsLocalNetworking':True},
 'NSAppleEventsUsageDescription':'AHAS uses macOS file-selection dialogs for local compression and extraction.'
}
(RES.parent/'Info.plist').write_bytes(plistlib.dumps(info,sort_keys=False))
(RES.parent/'PkgInfo').write_bytes(b'APPL????')

# Programmatic icon; a single clear mark, not an external asset.
canvas = Image.new('RGBA',(1024,1024),(0,0,0,0))
d = ImageDraw.Draw(canvas)
d.rounded_rectangle((94,105,930,941),radius=188,fill=(8,17,6,50))
d.rounded_rectangle((90,80,934,924),radius=185,fill=(25,51,62,255))
d.rounded_rectangle((230,216,626,668),radius=72,fill=(170,135,80,255))
d.rounded_rectangle((376,354,772,806),radius=72,fill=(33,105,87,255))
d.line([(500,440),(500,638),(650,638)],fill=(245,243,237),width=44,joint='curve')
d.polygon([(610,570),(690,638),(610,706)],fill=(245,243,237))
chunks=[]
import io
for tag,size in [('ic07',128),('ic08',256),('ic09',512),('ic10',1024)]:
    buf=io.BytesIO();canvas.resize((size,size),Image.Resampling.LANCZOS).save(buf,format='PNG')
    data=buf.getvalue();chunks.append(tag.encode()+struct.pack('>I',len(data)+8)+data)
body=b''.join(chunks)
(RES/'AHAS.icns').write_bytes(b'icns'+struct.pack('>I',len(body)+8)+body)

# Finder layout for the mounted volume.
from ds_store import DSStore
with DSStore.open(str(STAGE/'.DS_Store'),'w+') as store:
    store['.']['bwsp'] = ('blob',plistlib.dumps({'ShowToolbar':False,'ShowStatusBar':False,'ShowPathbar':False,'ShowSidebar':False,'WindowBounds':'{{240, 160}, {680, 470}}','ContainerShowSidebar':False},fmt=plistlib.FMT_BINARY))
    store['.']['icvp'] = ('blob',plistlib.dumps({'viewOptionsVersion':1,'backgroundType':1,'backgroundColorRed':0.93,'backgroundColorGreen':0.96,'backgroundColorBlue':0.90,'gridOffsetX':0.0,'gridOffsetY':0.0,'gridSpacing':100.0,'arrangeBy':'none','showIconPreview':True,'showItemInfo':False,'labelOnBottom':True,'textSize':13.0,'iconSize':112.0},fmt=plistlib.FMT_BINARY))
    store['.']['vSrn'] = ('long',1)
    store['AHAS.app']['Iloc'] = (175,165)
    store['Applications']['Iloc'] = (495,165)
    store['READ ME FIRST.txt']['Iloc'] = (335,340)

# hfsplus addall dereferences links; record then create links explicitly afterward.
links=[]
for p in STAGE.rglob('*'):
    if p.is_symlink():
        links.append({'path':'/'+str(p.relative_to(STAGE)), 'target':os.readlink(p)})
        p.unlink()
links.append({'path':'/Applications','target':'/Applications'})
(WORK/'symlinks.json').write_text(json.dumps(links,indent=2))
print('Bundle staged:',STAGE)
print('Payload file bytes:',sum(p.stat().st_size for p in STAGE.rglob('*') if p.is_file()))
print('Links to create:',len(links))
