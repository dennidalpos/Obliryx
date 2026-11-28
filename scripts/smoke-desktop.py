"""Synthetic native WebView2 smoke. Never points at the user's data directory.

Run with a development environment containing desktop + demo dependencies after
npm run build. The debug port exists only in this test process, not in the app.
Evidence stays in ignored .desktop-work and .impeccable/review folders.
"""
import json
import secrets
import socket
import os
import subprocess
import sys
import time
import uuid
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from obliryx.analysis import analyze_email
from obliryx.desktop import DesktopAPI
from obliryx.desktop_host import run_window
from obliryx.store import Store


def main():
    import webview
    from playwright.sync_api import sync_playwright
    folder = ROOT / '.desktop-work' / ('native-smoke-' + uuid.uuid4().hex)
    folder.mkdir(parents=True)
    evidence = ROOT / '.impeccable' / 'review'
    evidence.mkdir(parents=True, exist_ok=True)
    phrase = secrets.token_hex(16)
    vault = folder / 'archivio sintetico.sqlite3'
    with closing(Store(vault, phrase, ledger_dir=folder / 'action-state')) as store:
        for name, subject in [('Notizie Esempio', 'Newsletter sintetica'), ('Fonte di prova', '<script>window.hostile=true</script>'), ('Aggiornamenti locali', 'Una fonte da verificare')]:
            raw = (f'From: {name} <news@example.invalid>\r\nTo: reader@example.invalid\r\n'
                   f'Subject: {subject}\r\nList-Id: <{secrets.token_hex(5)}.example.invalid>\r\n'
                   'List-Unsubscribe: <https://example.invalid/leave?token=synthetic>\r\n\r\nSynthetic body').encode()
            store.save(analyze_email(raw), b'eml\x00' + raw)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    webview.settings['REMOTE_DEBUGGING_PORT'] = port
    result = {'status': 'not-run', 'checks': []}

    def exercise(window):
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
                page = browser.contexts[0].pages[0]
                page.get_by_role('heading', name='Quali dati vuoi cercare?').wait_for()
                page.get_by_role('button', name='Apri archivio precedente', exact=True).click()
                page.wait_for_selector('text=Crea nuovo')
                page.screenshot(path=str(evidence / 'onboarding.png'), full_page=True)
                page.get_by_role('button', name='Apri esistente', exact=True).click()
                page.get_by_label('Percorso dell’archivio').fill(str(vault))
                page.get_by_label('Passphrase', exact=True).fill(phrase)
                page.get_by_role('button', name='Apri archivio', exact=True).click()
                page.get_by_role('heading', name='Riscontri', exact=True).wait_for()
                page.locator('.finding-row').first.click()
                page.get_by_role('heading', name='Il prossimo passo').wait_for()
                page.screenshot(path=str(evidence / 'desktop.png'), full_page=True)
                assert page.evaluate('window.hostile === undefined')
                assert page.evaluate('localStorage.length === 0 && sessionStorage.length === 0')
                result['checks'].extend(['native unlock', 'native list/detail', 'HTML treated as text', 'no web storage'])
                page.get_by_role('button', name='Rivedi l’iscrizione', exact=True).first.click()
                page.get_by_label('Riconosci l’iscrizione?').select_option('non_riconosciuta')
                page.get_by_role('button', name='Continua', exact=True).click()
                page.get_by_text('Attività completata', exact=True).wait_for()
                result['checks'].append('review through real Python bridge')
                page.get_by_role('button', name='Chiudi attività').click()
                page.get_by_role('button', name='Archivio', exact=True).click()
                page.get_by_role('button', name='Crea una copia cifrata', exact=False).click()
                page.get_by_label('Nuovo file di destinazione').fill(str(folder / 'copia.sqlite3'))
                page.get_by_role('button', name='Continua', exact=True).click()
                page.get_by_role('heading', name='Controlla prima di confermare').wait_for()
                page.screenshot(path=str(evidence / 'approval.png'), full_page=True)
                page.get_by_label('Digita CONFERMO per approvare questo passaggio').fill('CONFERMO')
                page.get_by_role('button', name='Approva questo passaggio').click()
                page.get_by_text('Attività completata', exact=True).wait_for()
                assert (folder / 'copia.sqlite3').is_file()
                result['checks'].append('backup approval through real bridge')
                page.get_by_role('button', name='Chiudi attività').click()
                page.get_by_role('button', name='Riscontri', exact=True).click()
                for width, height, filename in [(1920,1080,'wide.png'), (640,720,'narrow.png')]:
                    page.set_viewport_size({'width':width, 'height':height})
                    time.sleep(.2)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), filename
                    page.screenshot(path=str(evidence / filename), full_page=True)
                page.set_viewport_size({'width':1280,'height':720})
                page.context.new_cdp_session(page).send('Emulation.clearDeviceMetricsOverride')
                result['checks'].append('1920/640 layout')
                if window is not None:
                    from System import Action
                    window.native.Invoke(Action(lambda: setattr(window.native.webview, 'ZoomFactor', 2.0)))
                    time.sleep(.3)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'native 200% zoom overflow'
                    page.evaluate('scrollTo(0,0)')
                    # CDP misinterprets native zoom coordinates; capture natively.
                    from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
                    from System.IO import FileStream, FileMode
                    for filename, detail in [('zoom-200.png', False), ('zoom-200-detail.png', True)]:
                        if detail:
                            page.locator('.finding-detail').scroll_into_view_if_needed()
                        stream = FileStream(str(evidence / filename), FileMode.Create)
                        tasks = []
                        window.native.Invoke(Action(lambda: tasks.append(window.native.webview.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, stream))))
                        tasks[0].Wait()
                        stream.Close()
                    result['zoom_metrics'] = page.evaluate('({viewport:innerWidth, content:document.documentElement.scrollWidth, zoom:devicePixelRatio})')
                    window.native.Invoke(Action(lambda: setattr(window.native.webview, 'ZoomFactor', 1.0)))
                    result['checks'].append('native 200% zoom layout')
                page.get_by_role('button', name='Blocca archivio', exact=True).click()
                page.get_by_role('heading', name='Il tuo archivio', exact=True).wait_for()
                assert not page.locator('.finding-row').count()
                result['checks'].append('lock removes decrypted UI')
                # Native navigation guard cancels even script-initiated external navigation.
                url = page.url
                page.evaluate("location.href='https://outside.invalid/'")
                time.sleep(.2)
                assert page.url == url
                assert page.evaluate('window.pywebview.api.status().then(r => r.ok)')
                result['checks'].append('external navigation blocked')
                result['status'] = 'passed'
                browser.close()
        except Exception as exc:
            result['status'] = 'failed'
            result['error'] = str(exc)
        finally:
            (folder / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            print(json.dumps(result, ensure_ascii=True), flush=True)
            if window is not None:
                # Let pending bridge callbacks drain before disposing the native host.
                time.sleep(.5)
                window.destroy()

    if len(sys.argv) == 3 and sys.argv[1] == '--executable':
        executable = Path(sys.argv[2]).resolve()
        environment = {**os.environ, 'LOCALAPPDATA':str(folder / 'profile'),
                       'WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS':f'--remote-debugging-port={port}'}
        log = (folder / 'process.log').open('w', encoding='utf-8')
        process = subprocess.Popen([str(executable)], env=environment, stdout=log, stderr=log)
        try:
            from urllib.request import urlopen
            for _ in range(100):
                try:
                    with urlopen(f'http://127.0.0.1:{port}/json/version', timeout=.5):
                        break
                except OSError:
                    time.sleep(.1)
            exercise(None)
        finally:
            process.terminate()
            process.wait(timeout=15)
            log.close()
    else:
        run_window(DesktopAPI(folder), ROOT / 'frontend' / 'dist', width=1280, height=720, ready=exercise)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
