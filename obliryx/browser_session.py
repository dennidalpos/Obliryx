"""A native WebView2 child window. Remote pages never get a Python/pywebview bridge.

Construction happens on the application's UI thread; operations wait off that thread.
Only fixed read-only scripts and reviewed procedure scripts may be evaluated.
"""
import json
import threading
import time
import uuid
from urllib.parse import urlencode, urlsplit

from .web_discovery import public_url


SNAPSHOT = r"""(() => {
 const visible = e => !!(e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
 const text = (document.body?.innerText || '').slice(0, 200000);
 const challenge = [...document.querySelectorAll('iframe,input,[class],[id]')].some(e =>
   visible(e) && /captcha|recaptcha|hcaptcha|turnstile/i.test((e.id||'')+' '+(e.className||'')+' '+(e.src||'')))
   || /verify you are human|verifica di essere umano|access denied|unusual traffic|verifying your browser/i.test(text);
 return {url: location.href, text, challenge,
   password: [...document.querySelectorAll('input[type=password]')].some(visible),
   links: [...document.querySelectorAll('a[href]')].filter(visible).slice(0,300).map(a=>({url:a.href}))};
})()"""


class BrowserSession:
    def __init__(self, host, directory):
        self.host, self.directory = host, directory
        self._form = self._view = self._label = None
        self._ready = threading.Event()
        self._loaded = threading.Event()
        self._error = False
        self._hooks = []
        self._target = None
        self._effect_url = None
        self._effect_admitted = False
        self._effect_body = None
        self._trusted_commands = False
        self._closed = False
        self._nav_lock = threading.Lock()
        self._ui(self._create)
        if not self._ready.wait(20) or self._error:
            raise ValueError("Il browser integrato non si è avviato. Verifica WebView2.")

    def _ui(self, function):
        from System import Action
        if self.host.native.IsDisposed:
            return
        self.host.native.Invoke(Action(function))

    def _create(self):
        from System.Windows.Forms import Form, DockStyle, Label, FlowLayoutPanel, Button, CloseReason
        from Microsoft.Web.WebView2.WinForms import WebView2, CoreWebView2CreationProperties
        form, view = Form(), WebView2()
        form.Text = "Obliryx — Browser isolato"
        form.Width, form.Height = 1024, 760
        form.Owner = self.host.native
        label = Label()
        label.Dock, label.Height, label.AutoEllipsis = DockStyle.Top, 42, True
        panel = FlowLayoutPanel()
        panel.Dock, panel.Height = DockStyle.Bottom, 48
        close = Button()
        close.Text, close.Width = "Torna all’app", 150
        close.Click += lambda *_: form.Hide()
        panel.Controls.Add(close)
        props = CoreWebView2CreationProperties()
        # Distinct environment and InPrivate profile; no automatic recursive cleanup.
        props.UserDataFolder = str(self.directory / ("browser-" + uuid.uuid4().hex))
        props.set_IsInPrivateModeEnabled(True)
        view.CreationProperties = props
        view.Dock = DockStyle.Fill
        form.Controls.Add(view)
        form.Controls.Add(label)
        form.Controls.Add(panel)
        self._form, self._view, self._label = form, view, label

        def initialized(_sender, event):
            try:
                if not event.IsSuccess:
                    self._error = True
                    return
                from Microsoft.Web.WebView2.Core import CoreWebView2WebResourceContext
                core = view.CoreWebView2
                core.Settings.IsWebMessageEnabled = False
                core.Settings.AreHostObjectsAllowed = False
                core.Settings.AreDevToolsEnabled = False
                core.Settings.AreDefaultContextMenusEnabled = False
                core.Settings.IsPasswordAutosaveEnabled = False
                core.Settings.IsGeneralAutofillEnabled = False
                core.NewWindowRequested += popup
                core.DownloadStarting += download
                core.PermissionRequested += permission
                core.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All)
                core.WebResourceRequested += resource
                self._hooks.extend([popup, download, permission, resource])
            except Exception:
                self._error = True
            finally:
                self._ready.set()

        def starting(_sender, event):
            self._loaded.clear()
            try:
                valid = public_url(str(event.Uri))
                self._label.Text = urlsplit(valid).netloc + " — Browser separato dai dati dell’app"
            except (ValueError, OSError):
                event.Cancel = True
                self._error = True
                self._loaded.set()

        def completed(_sender, event):
            self._error = not event.IsSuccess
            self._loaded.set()

        def popup(_sender, event):
            event.Handled = True
            # No popup or OS browser opened by untrusted page code.

        def download(_sender, event):
            event.Cancel = True

        def permission(_sender, event):
            from Microsoft.Web.WebView2.Core import CoreWebView2PermissionState
            event.State = CoreWebView2PermissionState.Deny

        def resource(_sender, event):
            stage = 'destination'
            try:
                request = event.Request
                uri = str(request.Uri)
                if uri.startswith(("data:", "blob:")):
                    return
                public_url(uri)
                if str(request.Method) not in {"GET", "HEAD", "OPTIONS"}:
                    if not self._trusted_commands:
                        if uri != self._effect_url or str(request.Method) != "POST" or self._effect_admitted:
                            raise ValueError("Invio non approvato.")
                        from System import Array, Byte
                        from System.IO import MemoryStream
                        raw = urlencode(self._effect_body).encode('ascii')
                        if len(raw) > 16384:
                            raise ValueError("Contenuto oltre il limite approvato.")
                        # Chromium's COM request stream does not support .NET Read.
                        # Replace it with precisely the approved fields instead of
                        # allowing scripts to attach hidden or changed values.
                        stage = 'replace'
                        request.Content = MemoryStream(Array[Byte](raw))
                        request.Headers.SetHeader('Content-Type', 'application/x-www-form-urlencoded')
                    self._effect_admitted = True
            except Exception as exc:
                self._blocked_reason = stage + ': ' + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
                event.Response = view.CoreWebView2.Environment.CreateWebResourceResponse(None, 403, "Blocked", "")

        def closing(_sender, event):
            if not self._closed and event.CloseReason == CloseReason.UserClosing:
                event.Cancel = True
                form.Hide()
            elif event.CloseReason != CloseReason.UserClosing:
                self._closed = True
                self._trusted_commands = False

        view.CoreWebView2InitializationCompleted += initialized
        view.NavigationStarting += starting
        view.NavigationCompleted += completed
        form.FormClosing += closing
        self._hooks.extend([initialized, starting, completed, closing])
        form.Show()
        view.EnsureCoreWebView2Async(None)

    def navigate(self, url, cancelled=None):
        url = public_url(url)
        with self._nav_lock:
            self._effect_url = None
            self._effect_admitted = False
            self._trusted_commands = False
            self._target = url
            self._error = False
            self._loaded.clear()
            self._ui(lambda: (self._form.Show(), self._view.CoreWebView2.Navigate(url)))
            deadline = time.monotonic() + 25
            while not self._loaded.wait(.1):
                if (cancelled and cancelled.is_set()) or self._closed:
                    raise ValueError("Consultazione interrotta.")
                if time.monotonic() > deadline:
                    self._ui(lambda: self._view.CoreWebView2.Stop())
                    raise ValueError("Tempo di consultazione scaduto.")
            if self._error:
                raise ValueError("Pagina non disponibile nel browser integrato.")
            # Give asynchronous rendering time to settle. An empty or continuously
            # changing page is not a valid negative observation.
            deadline = time.monotonic() + 4
            earliest = time.monotonic() + .6
            previous, stable_since = None, time.monotonic()
            while time.monotonic() < deadline:
                if cancelled and cancelled.is_set():
                    raise ValueError("Consultazione interrotta.")
                snapshot = self.snapshot()
                if snapshot.get('challenge') or snapshot.get('password'):
                    return snapshot
                signature = snapshot.get('text','')
                if signature != previous:
                    previous, stable_since = signature, time.monotonic()
                if signature.strip() and time.monotonic() >= earliest and time.monotonic()-stable_since >= .35:
                    return {**snapshot, 'settled':True}
                time.sleep(.1)
            return {**snapshot, 'settled':False}

    def _evaluate(self, script):
        tasks = []
        self._ui(lambda: tasks.append(self._view.CoreWebView2.ExecuteScriptAsync(script)))
        if not tasks[0].Wait(15000):
            raise ValueError("La pagina non risponde.")
        try:
            return json.loads(str(tasks[0].Result))
        except (ValueError, TypeError):
            raise ValueError("Risposta della pagina non leggibile.") from None

    def snapshot(self):
        snapshot = self._evaluate(SNAPSHOT)
        if not isinstance(snapshot, dict):
            raise ValueError("Pagina non leggibile.")
        public_url(snapshot.get("url", ""))
        return snapshot

    def inspect(self, adapter):
        return self._evaluate(adapter.inspect_script)

    def submit(self, adapter, values):
        self._effect_url = adapter.submit_url
        self._effect_body = {name: values[category] for name, category in adapter.fields}
        self._effect_admitted = False
        result = self._evaluate(adapter.submit_script(values))
        if not result:
            return "contract_changed"
        return "submitted"

    def completion(self, adapter):
        deadline = time.monotonic() + 8
        result = {}
        while time.monotonic() < deadline:
            try:
                result = self.snapshot()
            except ValueError:
                time.sleep(.1)
                continue
            detail = self._evaluate("(() => {const e=document.getElementById(" + json.dumps(adapter.success_id) + "); return e && e.getClientRects().length ? {completion_id:e.id,completion_text:e.innerText.trim()} : {};})()")
            result.update(detail or {})
            if adapter.completed(result) or result.get("challenge"):
                break
            time.sleep(.2)
        self._effect_url = None
        self._effect_body = None
        return result

    def assist(self, url, cancelled=None):
        snapshot = self.navigate(url, cancelled)
        # User takes control after the batch approval. No automatic fill or click.
        self._trusted_commands = True
        self.show()
        return snapshot

    def show(self):
        self._ui(lambda: (self._form.Show(), self._form.Activate()))

    def suspend(self):
        self._trusted_commands = False
        self._effect_url = None
        self._effect_body = None
        if self._view is not None and not self._closed:
            self._ui(lambda: (self._view.CoreWebView2.Stop(), self._form.Hide()))

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._ui(lambda: (self._view.Dispose(), self._form.Dispose()))
