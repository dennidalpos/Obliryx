# Obliryx

Archivio personale dei riscontri di mailing list, marketing ed esposizione dei propri dati.

## Scopo

Analizza messaggi `.eml` ed esportazioni `.mbox` della tua posta, consente di aggiungere riscontri Web con la fonte e guida le richieste di opposizione, cancellazione o disiscrizione. I messaggi originali restano nei file di partenza; l'archivio SQLite cifra riscontri, URL e anteprime. Ogni invio richiede una conferma individuale. L'app desktop Windows e la CLI (Python) condividono questi principi. La versione 0.1.0.dev0 è sperimentale.

## Requisiti

- Python 3.11 o successivo per la CLI.
- Per l'installer desktop: Python 3.13 x64, Node 22 LTS e Inno Setup 6; l'app installata non richiede Python.

## Primo avvio

Da PowerShell, nella cartella del progetto:

```powershell
.\Avvia-Obliryx.ps1
```

Il menu crea `.venv` se manca e guida importazione, ricerche, revisione, bozze e disiscrizioni. In alternativa:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m obliryx --help
```

L'archivio è in `%LOCALAPPDATA%\obliryx` (Windows) o `~/.local/share/obliryx`; usa una passphrase lunga e unica, perché perderla significa perdere l'accesso ai riscontri.

## Uso

Il percorso è: **dati → analisi → selezione → riepilogo approvato → interventi**. Esempi con la CLI:

```powershell
obliryx import-mbox ESPORTAZIONE.mbox   # analisi offline
obliryx campaigns                        # raggruppa per mittente
obliryx draft ID                         # bozza di opposizione, cancellazione o accesso
```

I riscontri vanno verificati alla fonte. Nessun broker del catalogo è dichiarato automatizzato: le procedure sono manuali. Tutti i comandi, il backup e il recupero sono in [REFERENCE.md](REFERENCE.md).

## Build e test

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
scripts/build-desktop.ps1   # installer desktop di sviluppo
```

## Documentazione e sicurezza

[Guida desktop](docs/desktop.md) · [Copertura delle funzioni](docs/desktop-coverage.md) · [Riferimento completo](REFERENCE.md) · [Segnalazioni di sicurezza](SECURITY.md) · [Licenza](LICENSE) (MIT).
