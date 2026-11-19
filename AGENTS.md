<!-- secondbrain:repository:begin -->
Common directives applied: revision **1.5** — 2026-11-19. <!-- secondbrain:source global=BF1230F0D495F6838C89A2E7CAE002840CBC178B808D896A90A8F93357CABEFE workstation=2B4198D3D9F66B2EC4AD159DC7889F6C21AD64C5E025B99005D26122D6E5AEDB -->
## SecondBrain

Repository knowledge lives in the SecondBrain dossier; code, guides, and publishable assets stay here. This block is generated: write project rules outside it, because a sync replaces everything inside.

- Load the slim startup with MCP get_startup_context or the startup mode of the SecondBrain knowledge tool, and follow its references for detail. If the checkout is unreachable, report the dossier as unavailable and continue from the repository files.
- Write only to this repository's dossier `repos/<repo>/`, only through SecondBrain scripts or MCP write tools. Work folders come from the work tool's init mode; sessions, retention, and cleanup rules load from `sb prompt`.
- Commits, pushes, deletions, and publication require specific authorization.
<!-- secondbrain:repository:end -->

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

## Git workflow (push policy)

- The repository owner is an admin and changes are verified locally before any push. When a push is authorized, push directly to `main` and do not open a pull request. This applies only to pushes the user has authorized; it does not authorize committing or pushing on its own. If anything is unclear (failed checks, unexpected remote state, protected-branch rejection), stop and ask.
