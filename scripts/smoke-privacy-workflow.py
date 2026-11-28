"""Real Windows WebView2 test, synthetic intercepted HTTPS only; no live services.

Run with .desktop-work/venv/Scripts/python.exe after npm run build.
Evidence and the isolated Windows-protected vault stay in .desktop-work/.
"""
import json
import faulthandler
import os
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from obliryx.browser_procedures import BrowserProcedure
from obliryx.browser_session import BrowserSession
from obliryx.desktop import DesktopAPI
from obliryx.desktop_host import run_window
from obliryx.free_sources import FreeSources

PAGE = "https://fixture.example.invalid/request"
DONE = "https://fixture.example.invalid/done"
ADAPTER = BrowserProcedure('synthetic-request', '1', PAGE, DONE, 'privacy', 'send',
                           (('email','email'),), 'receipt', 'Request received', 'Richiesta sintetica')
HTML = '<html><body><p id="identity">Caricamento…</p><script>setTimeout(()=>document.getElementById("identity").textContent="reader@example.invalid",200)</script><form id="privacy" method="post" action="/done"><input type="email" name="email" required><button id="send" type="submit">Invia richiesta sintetica</button></form></body></html>'
MANUAL = '<html><body><h1>Verifica sintetica</h1><p>reader@example.invalid</p><label>Codice di prova<input id="code"></label><button onclick="document.getElementById(\'done\').textContent=\'Verifica completata\'">Conferma verifica</button><p id="done"></p></body></html>'


def main():
    faulthandler.dump_traceback_later(70, exit=True)
    import webview
    from playwright.sync_api import sync_playwright
    directory = ROOT / '.desktop-work' / ('workflow-smoke-' + uuid.uuid4().hex)
    directory.mkdir(parents=True)
    api = DesktopAPI(directory)
    api._workflow.procedures = {ADAPTER.identifier: ADAPTER}
    output = {'status':'not-run', 'checks':[]}
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port = sock.getsockname()[1]
    webview.settings['REMOTE_DEBUGGING_PORT'] = port
    requests = []
    def synthetic_json(host, path):
        return {'items':[{'login':'synthetic-profile'}],'total_count':1} if host=='api.github.com' else {'query':{'search':[]}}
    api._workflow.free_sources = FreeSources(request=synthetic_json)

    def validate(url):
        from urllib.parse import urlsplit
        if (urlsplit(url).hostname != 'fixture.example.invalid' and url != 'https://github.com/synthetic-profile' and url != 'https://github.com/favicon.ico') or not url.startswith('https://'):
            raise ValueError('Only synthetic test pages are permitted')
        return url

    def browser_factory(window):
        browser = BrowserSession(window, directory / 'browser-sessions')
        def install():
            from System import Array, Byte
            from System.IO import MemoryStream
            def intercept(_sender, event):
                request = event.Request
                uri = str(request.Uri)
                validate(uri)
                requests.append((str(request.Method),uri))
                if event.Response is not None:
                    requests.append(('BLOCKED',uri))
                    output['blocked_reason'] = getattr(browser,'_blocked_reason','unknown')
                    return
                html = '<html><body><p id="receipt">Request received</p></body></html>' if uri==DONE else MANUAL if uri.endswith('/manual') else HTML
                stream = MemoryStream(Array[Byte](html.encode()))
                event.Response = browser._view.CoreWebView2.Environment.CreateWebResourceResponse(stream,200,'OK','Content-Type: text/html; charset=utf-8\r\nCache-Control: no-store')
            browser._view.CoreWebView2.WebResourceRequested += intercept
            browser._hooks.append(intercept)
        browser._ui(install)
        original_submit, original_completion = browser.submit, browser.completion
        def submit(*args):
            try:
                result = original_submit(*args)
                output['native_submit_result'] = result
                return result
            except Exception as exc:
                output['native_submit_error'] = str(exc)
                raise
        def completion(*args):
            try:
                result = original_completion(*args)
                output['native_completion_result'] = result
                return result
            except Exception as exc:
                output['native_completion_error'] = str(exc)
                raise
        browser.submit, browser.completion = submit, completion
        return browser

    def exercise(window):
        try:
            api._workflow.browser_factory = lambda: browser_factory(window)
            with sync_playwright() as playwright:
                chrome = playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
                page = chrome.contexts[0].pages[0]
                page.get_by_role('heading',name='Quali dati vuoi cercare?').wait_for()
                assert (directory/'desktop-key.dpapi').is_file()
                assert (directory/'desktop-history.sqlite3').is_file()
                assert not page.get_by_label('Passphrase',exact=True).count()
                output['checks'].append('native DPAPI startup without password')
                page.get_by_label('Email',exact=True).fill('reader@example.invalid')
                page.get_by_role('button',name='Avvia analisi',exact=True).click()
                page.get_by_role('heading',name='Scegli dove intervenire').wait_for()
                page.screenshot(path=str(directory/'results.png'),full_page=True)
                assert page.get_by_text('2 di 3 ricerche consultate',exact=False).count()
                output['checks'].append('free APIs with synthetic responses discover pages; blocked search is explicit')
                page.get_by_text('Hai trovato una pagina con i tuoi dati?',exact=True).click()
                page.get_by_label('Indirizzo della pagina').fill(PAGE)
                page.get_by_role('button',name='Verifica pagina',exact=True).click()
                deadline = time.monotonic()+30
                while api._workflow.snapshot()['busy'] and time.monotonic()<deadline:
                    time.sleep(.1)
                page.get_by_text('Testo corrispondente trovato',exact=True).first.wait_for()
                browser = api._workflow._browser
                assert browser._evaluate('typeof window.pywebview') == 'undefined'
                settings = []
                browser._ui(lambda:settings.append((browser._view.CoreWebView2.Settings.AreHostObjectsAllowed,browser._view.CoreWebView2.Settings.IsWebMessageEnabled,browser._view.CoreWebView2.Profile.IsInPrivateModeEnabled)))
                assert settings == [(False,False,True)], settings
                output['checks'].extend(['real isolated browser visits synthetic dynamic page','no remote bridge or web messages; InPrivate profile'])
                # Select both automatic and assisted synthetic broker procedures.
                page.get_by_label('Broker automatico sintetico',exact=True).check()
                page.get_by_label('Broker assistito sintetico',exact=True).check()
                page.get_by_role('button',name='Controlla gli interventi selezionati',exact=True).click()
                page.get_by_role('heading',name='Controlla prima di approvare').wait_for()
                page.screenshot(path=str(directory/'approval.png'),full_page=True)
                page.get_by_label('Approvo gli interventi e i dati indicati in questo riepilogo.').check()
                page.get_by_role('button',name='Avvia gli interventi approvati',exact=True).click()
                deadline = time.monotonic()+35
                while not api._workflow.snapshot()['assistance'] and time.monotonic()<deadline:
                    time.sleep(.1)
                state = api._workflow.snapshot()
                assert state['assistance'], state
                assert state['operations'][0]['status']=='accepted',state
                assert len([r for r in requests if r==('POST',DONE)])==1,requests
                output['checks'].append('one approved native POST, recognized receipt, automatic before assisted')
                # Exercise the user handoff inside the real remote WebView2.
                browser._evaluate("document.getElementById('code').value='123456'; document.querySelector('button').click(); true")
                page.get_by_role('button',name='Continua',exact=True).click()
                page.get_by_role('heading',name='Esito degli interventi',exact=True).wait_for()
                output['checks'].append('assisted handoff and continuation without automatic resubmission')
                for width,height,name in [(1280,800,'desktop'),(640,720,'narrow')]:
                    page.set_viewport_size({'width':width,'height':height})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),name
                    page.screenshot(path=str(directory/(name+'.png')),full_page=True)
                assert page.evaluate('localStorage.length === 0 && sessionStorage.length === 0')
                output['checks'].append('native 1280/640 layout; no web storage')
                page.get_by_role('button',name='Chiudi sessione',exact=True).click()
                page.get_by_role('heading',name='Le tue tracce sul Web, un passo alla volta.').wait_for()
                assert api._workflow._values == {}
                output['checks'].append('lock clears identity and approved queue')
                output['status']='passed'
                chrome.close()
        except Exception as error:
            output['status']='failed'
            output['error']=str(error)
        finally:
            output['requests'] = requests
            (directory/'result.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
            print(json.dumps({**output,'evidence':str(directory)}),flush=True)
            window.destroy()

    def row(identifier,title,url):
        return {'id':identifier,'controller':title,'countries':['IT'],'source':url,'action':'cancellazione',
                'reviewed_on':'2026-11-13','channel':{'kind':'web','destination':url,'effect':'Richiesta sintetica'}}
    catalog = {'procedures':[row('synthetic-request','Broker automatico sintetico',PAGE),row('synthetic-assisted','Broker assistito sintetico','https://fixture.example.invalid/manual')]}
    with patch('obliryx.privacy_workflow.load_catalog',return_value=catalog), patch('obliryx.privacy_workflow.public_url',side_effect=validate), patch('obliryx.browser_session.public_url',side_effect=validate):
        run_window(api,ROOT/'frontend'/'dist',ready=exercise)
    return 0 if output['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())
