"""Native AppKit + WebKit host. Runs inside the bundled arm64 CPython runtime.
No PyObjC or pip dependencies. macOS-only code; main thread owns AppKit.
"""
from __future__ import annotations
import ctypes as C
import os
from pathlib import Path
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'app'))
from compactlocal import server, __version__

ID = C.c_void_p
BOOL = C.c_bool
INTEGER = C.c_long
ULONG = C.c_ulong
DOUBLE = C.c_double

class Point(C.Structure):
    _fields_ = [('x', DOUBLE), ('y', DOUBLE)]

class Size(C.Structure):
    _fields_ = [('width', DOUBLE), ('height', DOUBLE)]

class Rect(C.Structure):
    _fields_ = [('origin', Point), ('size', Size)]

objc = C.CDLL('/usr/lib/libobjc.A.dylib')
C.CDLL('/System/Library/Frameworks/AppKit.framework/AppKit')
C.CDLL('/System/Library/Frameworks/WebKit.framework/WebKit')
objc.objc_getClass.argtypes = [C.c_char_p]
objc.objc_getClass.restype = ID
objc.sel_registerName.argtypes = [C.c_char_p]
objc.sel_registerName.restype = ID
objc.objc_allocateClassPair.argtypes = [ID, C.c_char_p, C.c_size_t]
objc.objc_allocateClassPair.restype = ID
objc.objc_registerClassPair.argtypes = [ID]
objc.class_addMethod.argtypes = [ID, ID, ID, C.c_char_p]
objc.class_addMethod.restype = BOOL
FUNCTIONS = {}
CALLBACKS = []
KEEP = []


def cls(name):
    result = objc.objc_getClass(name.encode())
    if not result:
        raise RuntimeError('macOS class unavailable: ' + name)
    return result


def sel(name):
    return objc.sel_registerName(name.encode())


def send(obj, selector, restype=ID, types=(), args=()):
    key = (restype, types)
    fn = FUNCTIONS.get(key)
    if fn is None:
        fn = C.CFUNCTYPE(restype, ID, ID, *types)(('objc_msgSend', objc))
        FUNCTIONS[key] = fn
    return fn(obj, sel(selector), *args)


def text(value):
    return send(cls('NSString'), 'stringWithUTF8String:', types=(C.c_char_p,), args=(str(value).encode('utf-8'),))


def new(name):
    obj = send(send(cls(name), 'alloc'), 'init')
    KEEP.append(obj)
    return obj


def void(obj, selector, types=(), args=()):
    return send(obj, selector, None, types, args)


def alert(title, detail, confirm=False):
    box = new('NSAlert')
    void(box, 'setMessageText:', (ID,), (text(title),))
    void(box, 'setInformativeText:', (ID,), (text(detail),))
    send(box, 'addButtonWithTitle:', types=(ID,), args=(text('Cancel operation and quit' if confirm else 'OK'),))
    if confirm:
        send(box, 'addButtonWithTitle:', types=(ID,), args=(text('Keep working'),))
    return send(box, 'runModal', INTEGER) == 1000


def running():
    with server.LOCK:
        return server.JOB.get('status') == 'running'


def add_method(k, name, result, argtypes, encoding, function):
    callback = C.CFUNCTYPE(result, ID, ID, *argtypes)(function)
    CALLBACKS.append(callback)
    if not objc.class_addMethod(k, sel(name), C.cast(callback, ID), encoding):
        raise RuntimeError('Could not register native method: ' + name)


def main():
    os.chdir(Path.home())
    pool = new('NSAutoreleasePool')
    app = send(cls('NSApplication'), 'sharedApplication')
    void(app, 'setActivationPolicy:', (INTEGER,), (0,))
    # The runtime executable is nested in Resources; use explicit app identity.
    send(cls('NSProcessInfo'), 'processInfo')
    void(send(cls('NSProcessInfo'), 'processInfo'), 'setProcessName:', (ID,), (text('AHAS'),))
    icon = send(send(cls('NSImage'), 'alloc'), 'initWithContentsOfFile:', types=(ID,), args=(text(HERE/'AHAS.icns'),))
    if icon:
        KEEP.append(icon)
        void(app, 'setApplicationIconImage:', (ID,), (icon,))

    http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    http.daemon_threads = True
    server.PREVIEW = False
    threading.Thread(target=http.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:' + str(http.server_port)

    delegate_class = objc.objc_allocateClassPair(cls('NSObject'), b'AHASNativeDelegate', 0)
    if not delegate_class:
        raise RuntimeError('Could not allocate app delegate')

    def should_terminate(_self, _cmd, _sender):
        if not running():
            return 1  # NSTerminateNow
        if not alert('An operation is still running', 'Quitting cancels the operation and removes incomplete output. Wait for cleanup before the app closes.', True):
            void(window, 'makeKeyAndOrderFront:', (ID,), (None,))
            return 0  # NSTerminateCancel
        server.CANCEL.set()
        # Reply later on the main run loop; never abandon a worker mid-write.
        timer = send(cls('NSTimer'), 'scheduledTimerWithTimeInterval:target:selector:userInfo:repeats:',
                     types=(DOUBLE, ID, ID, ID, BOOL), args=(0.2, _self, sel('waitForCleanup:'), None, True))
        KEEP.append(timer)
        return 2  # NSTerminateLater

    def wait_cleanup(_self, _cmd, timer):
        if not running():
            void(timer, 'invalidate')
            void(app, 'replyToApplicationShouldTerminate:', (BOOL,), (True,))

    def about(_self, _cmd, _sender):
        alert('AHAS '+__version__, 'Made by Ahas Nimsandu\n\nSolid .ahas archives, whole-file deduplication, extraction, verification, and a separate lossy Media Optimizer.\n\nRuns locally on your Mac. No uploads.\n\nNo universal 1,000× compression guarantee. macOS extended metadata and resource forks are not preserved.\n\nAd-hoc-signed experimental Apple Silicon build; not notarized. Test restoration before deleting originals.')

    def will_terminate(_self, _cmd, _notification):
        server.CANCEL.set()
        http.shutdown()

    def reopen(_self, _cmd, _sender, visible):
        if not visible:
            void(window, 'makeKeyAndOrderFront:', (ID,), (None,))
        return True

    add_method(delegate_class, 'applicationShouldHandleReopen:hasVisibleWindows:', BOOL, (ID, BOOL), b'B@:@B', reopen)
    add_method(delegate_class, 'applicationShouldTerminate:', INTEGER, (ID,), b'q@:@', should_terminate)
    add_method(delegate_class, 'applicationShouldTerminateAfterLastWindowClosed:', BOOL, (ID,), b'B@:@', lambda *_: True)
    add_method(delegate_class, 'applicationWillTerminate:', None, (ID,), b'v@:@', will_terminate)
    add_method(delegate_class, 'waitForCleanup:', None, (ID,), b'v@:@', wait_cleanup)
    add_method(delegate_class, 'showAbout:', None, (ID,), b'v@:@', about)
    objc.objc_registerClassPair(delegate_class)
    delegate = send(send(delegate_class, 'alloc'), 'init')
    KEEP.append(delegate)
    void(app, 'setDelegate:', (ID,), (delegate,))

    def item(title, action=None, key='', target=None):
        obj = send(send(cls('NSMenuItem'), 'alloc'), 'initWithTitle:action:keyEquivalent:',
                   types=(ID, ID, ID), args=(text(title), sel(action) if action else None, text(key)))
        KEEP.append(obj)
        if target:
            void(obj, 'setTarget:', (ID,), (target,))
        return obj

    def menu(title):
        obj = send(send(cls('NSMenu'), 'alloc'), 'initWithTitle:', types=(ID,), args=(text(title),))
        KEEP.append(obj)
        return obj

    def add(menu_obj, item_obj):
        void(menu_obj, 'addItem:', (ID,), (item_obj,))

    bar = menu('Main')
    app_menu = menu('AHAS')
    app_item = item('AHAS')
    void(app_item, 'setSubmenu:', (ID,), (app_menu,))
    add(bar, app_item)
    add(app_menu, item('About AHAS — Made by Ahas Nimsandu', 'showAbout:', target=delegate))
    add(app_menu, send(cls('NSMenuItem'), 'separatorItem'))
    add(app_menu, item('Hide AHAS', 'hide:', 'h', app))
    add(app_menu, item('Quit AHAS', 'terminate:', 'q', app))
    edit = menu('Edit')
    edit_item = item('Edit')
    void(edit_item, 'setSubmenu:', (ID,), (edit,))
    add(bar, edit_item)
    for title, action, key in [('Undo','undo:','z'),('Cut','cut:','x'),('Copy','copy:','c'),('Paste','paste:','v'),('Select All','selectAll:','a')]:
        add(edit, item(title, action, key))
    windows = menu('Window')
    window_item = item('Window')
    void(window_item, 'setSubmenu:', (ID,), (windows,))
    add(bar, window_item)
    add(windows, item('Minimize', 'performMiniaturize:', 'm'))
    add(windows, item('Zoom', 'performZoom:'))
    void(app, 'setWindowsMenu:', (ID,), (windows,))
    void(app, 'setMainMenu:', (ID,), (bar,))

    frame = Rect(Point(0, 0), Size(1180, 850))
    window = send(send(cls('NSWindow'), 'alloc'), 'initWithContentRect:styleMask:backing:defer:',
                  types=(Rect, ULONG, ULONG, BOOL), args=(frame, 1|2|4|8, 2, False))
    KEEP.append(window)
    void(window, 'setReleasedWhenClosed:', (BOOL,), (False,))
    void(window, 'setTitle:', (ID,), (text('AHAS · Made by Ahas Nimsandu'),))
    void(window, 'setContentMinSize:', (Size,), (Size(760, 600),))
    void(window, 'setFrameAutosaveName:', (ID,), (text('AHASMainWindow'),))
    configuration = new('WKWebViewConfiguration')
    view = send(send(cls('WKWebView'), 'alloc'), 'initWithFrame:configuration:',
                types=(Rect, ID), args=(frame, configuration))
    KEEP.append(view)
    if not view:
        raise RuntimeError('Could not create WebKit window')
    void(view, 'setAutoresizingMask:', (ULONG,), (2|16,))
    void(window, 'setContentView:', (ID,), (view,))
    nsurl = send(cls('NSURL'), 'URLWithString:', types=(ID,), args=(text(url),))
    request = send(cls('NSURLRequest'), 'requestWithURL:', types=(ID,), args=(nsurl,))
    send(view, 'loadRequest:', types=(ID,), args=(request,))
    void(window, 'center')
    void(window, 'makeKeyAndOrderFront:', (ID,), (None,))
    void(app, 'activateIgnoringOtherApps:', (BOOL,), (True,))
    send(app, 'run', None)
    http.server_close()
    void(pool, 'drain')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        import subprocess
        subprocess.run(['/usr/bin/osascript', '-e', 'display alert "AHAS could not start" message "See ~/Library/Logs/AHAS/app.log for details. This unsigned build requires an Apple Silicon Mac with macOS 11 or newer." as critical'])
        raise SystemExit(1)
