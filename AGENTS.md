<!-- secondbrain:repository:begin -->
Common directives applied: revision **1.3** — 2026-11-13. <!-- secondbrain:source global=6B4E10F48D98505DB4ABF6C08AD8BB01229A0D33FF844A2C91781D63F291B480 workstation=BD2E210B49B3B77000F570E6F6191DC694798722B50900E6C3864E3DBDD78FF7 -->
## SecondBrain

Repository knowledge lives in the SecondBrain dossier; code, guides, and publishable assets stay here.

- Load the slim startup with the SecondBrain checkout's scripts/knowledge.ps1 -Startup or MCP get_startup_context, and follow its references for detail. If the root is unreachable, report the dossier as unavailable.
- Write only to this repository's dossier `01-projects/<repo>/`, only through SecondBrain scripts or MCP write tools. Work folders come from scripts/work.ps1 -Init; sessions, retention, and cleanup rules load from `sb prompt`.
- Commits, pushes, deletions, and publication require specific authorization.

## Setup e controlli prima di chiudere

- Ambiente: `python -m venv .venv`, poi `.\.venv\Scripts\python.exe -m pip install -e .` (Python >= 3.11; su Linux/macOS `.venv/bin/python`).
- Controlli come in CI: `python -m unittest discover -s tests -v`, `python -m pip check`, `python -I -m obliryx --help`.
- Se tocchi `Avvia-Obliryx.ps1`: `.\tests\test_launcher.ps1` con Windows PowerShell 5.1 e con PowerShell 7.
- Se tocchi `obliryx/multistep_demo.py`: `python -m pip install -e ".[demo]"`, `python -m playwright install chromium`, poi `python -m unittest discover -s tests -p "test_multistep_demo.py" -v`.
- Non esistono linter o formatter configurati: non inventarli.

## Struttura e file da non modificare

- Pacchetto `obliryx/`: `cli.py` (comandi), `store.py` (archivio SQLite cifrato), `one_click.py`, `web_forms.py`, `imap_source.py`, `mail_import.py`, `network.py`, `broker_catalog.py`, `multistep_demo.py`.
- Test in `tests/` (`unittest`, un file `test_*.py` per area), con dati sintetici e server locali; nessun dato reale.
- Non modificare `build/`, `.venv/`, `.local/`: generati o locali, ignorati da Git.
- `obliryx/broker_procedures.json` è dato distribuito (package-data): vedi sezione catalogo.

## Catalogo broker

Se cambia una scheda in `obliryx/broker_procedures.json`, aggiorna versione, data di revisione e `review_sha256` con `review_fingerprint` da `obliryx.broker_catalog`: le schede con impronta vecchia vengono rifiutate. Verifica prima la fonte ufficiale del titolare. Eseguire `tests/test_broker_catalog.py`.

## Sicurezza del prodotto

- Non registrare in archivio, log o test valori cercati, passphrase, chiavi API o token IMAP: vengono chiesti a runtime e non salvati.
- Gli invii POST (one-click, moduli) richiedono conferme distinte, passano dal registro `action-state` e non seguono redirect né inviano cookie; non indebolire questi vincoli.
- Test e demo usano solo dati sintetici e server HTTPS/IMAP locali; non contattare servizi reali.
- Non versionare `*.eml`, `*.mbox`, `*.sqlite3*`, `.env`.
<!-- secondbrain:repository:end -->
