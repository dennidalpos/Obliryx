"""Windows host: restricted static assets, WebView2 and session-lock handling."""
import ctypes
import hashlib
import json
import mimetypes
import os
import secrets
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .cli import data_directory
from .desktop import DesktopAPI


@contextmanager
def asset_server(root):
    root = Path(root).resolve()
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            prefix = '/' + token + '/'
            path = unquote(urlsplit(self.path).path)
            if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}' or not path.startswith(prefix):
                self.send_error(404)
                return
            target = (root / (path[len(prefix):] or 'index.html')).resolve()
            if not target.is_relative_to(root) or not target.is_file() or target.suffix not in {'.html', '.js', '.css', '.svg', '.png', '.woff2'}:
                self.send_error(404)
                return
            content = target.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', {'.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html'}.get(target.suffix, mimetypes.guess_type(target.name)[0] or 'application/octet-stream'))
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'none'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *_):
            pass  # Asset URLs and paths are never logged.

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True, name='obliryx-assets')
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/{token}/index.html'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _message(text):
    ctypes.windll.user32.MessageBoxW(None, text, 'Obliryx', 0x10)


def _instance():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    identity = hashlib.sha256(str(data_directory().resolve()).casefold().encode()).hexdigest()[:24]
    handle = kernel.CreateMutexW(None, True, 'Global\\Obliryx-' + identity)
    if not handle:
        raise OSError('Impossibile riservare l’istanza desktop.')
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle(handle)
        raise ValueError('Obliryx è già aperto. Torna alla finestra esistente.')
    return kernel, handle


def run_window(api, assets, width=1280, height=800, ready=None):
    """Reusable by the native synthetic smoke test; no debug port in production."""
    import webview
    webview.settings['ALLOW_DOWNLOADS'] = False
    webview.settings['ALLOW_FILE_URLS'] = False
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = False
    webview.settings['IGNORE_SSL_ERRORS'] = False
    hooks = []
    with asset_server(assets) as url:
        window = webview.create_window('Obliryx — Archivio personale', url, js_api=api,
                                       width=width, height=height, min_size=(640, 480),
                                       background_color='#ffffff', text_select=True)
        api._window = window

        def secure_host():
            # Native setup runs on the UI thread before accepting navigation.
            import clr
            clr.AddReference('System')
            from Microsoft.Win32 import SystemEvents, SessionSwitchReason
            from System import Action

            def setup():
                control = window.native.webview
                browser = window.native.browser
                def navigation(_sender, event):
                    if str(event.Uri) != url:
                        event.Cancel = True
                def new_window(_sender, event):
                    event.Handled = True
                def session(_sender, event):
                    if event.Reason in (SessionSwitchReason.SessionLock, SessionSwitchReason.SessionLogoff,
                                        SessionSwitchReason.RemoteDisconnect, SessionSwitchReason.ConsoleDisconnect):
                        api.lock()
                control.NavigationStarting += navigation
                # pywebview otherwise reinjects/reset its bridge after cancelled
                # navigation too, invalidating callbacks in the still-local page.
                control.NavigationCompleted -= browser.on_navigation_completed
                def completed(sender, event):
                    if event.IsSuccess and str(sender.Source) == url:
                        browser.on_navigation_completed(sender, event)
                control.NavigationCompleted += completed
                # Registered before the page is interactive; no remote document
                # is ever navigated into the privileged bridge window.
                def core_ready(sender, event):
                    if event.IsSuccess:
                        sender.CoreWebView2.NewWindowRequested += new_window
                        sender.CoreWebView2.Settings.IsPasswordAutosaveEnabled = False
                        sender.CoreWebView2.Settings.IsGeneralAutofillEnabled = False
                control.CoreWebView2InitializationCompleted += core_ready
                if control.CoreWebView2:
                    control.CoreWebView2.NewWindowRequested += new_window
                    control.CoreWebView2.Settings.IsPasswordAutosaveEnabled = False
                    control.CoreWebView2.Settings.IsGeneralAutofillEnabled = False
                SystemEvents.SessionSwitch += session
                hooks.extend([navigation, new_window, session, core_ready, completed])
            window.native.Invoke(Action(setup))

        # before_show is synchronous. A failed guard must not leave a usable bridge.
        def setup_guard():
            try:
                secure_host()
            except Exception:
                api.lock()
                _message('Impossibile inizializzare i controlli della finestra. Chiudi e reinstalla Obliryx.')
                os._exit(1)
        window.events.before_show += setup_guard
        def enable_drop():
            from webview.dom import DOMEventHandler
            def dropped(event):
                files = event.get('dataTransfer', {}).get('files', [])
                if not files or not files[0].get('pywebviewFullPath'):
                    return
                path = files[0]['pywebviewFullPath']
                # The native DOM event supplies the path, never an HTML file name.
                window.evaluate_js('window.dispatchEvent(new CustomEvent("obliryx-drop", {detail:' + json.dumps(path) + '}))')
            window.dom.document.events.drop += DOMEventHandler(dropped, prevent_default=True)
        window.events.loaded += enable_drop
        if ready:
            ready_fired = threading.Event()
            def once_ready():
                if not ready_fired.is_set():
                    ready_fired.set()
                    ready(window)
            window.events.loaded += once_ready
        try:
            # Non-private profile avoids pywebview deleting a profile on shutdown.
            # App data, secrets and decrypted content are never stored in it.
            webview.start(gui='edgechromium', debug=False, private_mode=False,
                          storage_path=str(api._directory / 'webview-profile'))
        finally:
            if len(hooks) >= 3:
                from Microsoft.Win32 import SystemEvents
                SystemEvents.SessionSwitch -= hooks[2]
            api._close()


def main():
    if sys.platform != 'win32':
        raise SystemExit('La versione desktop richiede Windows 11 x64.')
    handle = None
    try:
        kernel, handle = _instance()
        assets = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'obliryx' / 'ui'
        if not (assets / 'index.html').is_file():
            if not getattr(sys, 'frozen', False):
                assets = Path(__file__).resolve().parent.parent / 'frontend' / 'dist'
            if not (assets / 'index.html').is_file():
                raise ValueError('Interfaccia non compilata. Usa l’installer oppure esegui scripts/build-desktop.ps1.')
        run_window(DesktopAPI(), assets)
    except Exception as exc:
        _message(str(exc) if isinstance(exc, ValueError) else 'Avvio non riuscito. Verifica WebView2 Runtime e reinstalla Obliryx.')
        return 1
    finally:
        if handle:
            kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.ReleaseMutex(handle)
            kernel.CloseHandle(handle)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
