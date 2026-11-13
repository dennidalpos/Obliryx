# Verifiche desktop — 13 novembre 2026

## Percorso Web a cinque fasi

Verifica locale aggiornata: **71 test Python riusciti**, controllo dipendenze riuscito, CLI in modalità isolata riuscita, build TypeScript/Vite e **4 test frontend riusciti**. I 19 test del nuovo percorso coprono fonti indisponibili, risultati API candidati, confronto della pagina, omonimi, limiti, deduplicazione, approvazioni scadute o revocate, ordinamento automatici/assistiti, CAPTCHA, cambi del contratto e timeout senza ripetizione.

`scripts/smoke-privacy-workflow.py` esercita l’app reale su Windows/WebView2: apertura DPAPI senza password, API gratuite con risposte sintetiche, pagina dinamica intercettata, browser InPrivate senza bridge/oggetti host/messaggi Web, un solo POST approvato e ricevuta riconosciuta, passaggio assistito e prosecuzione, layout 1280/640, assenza di Web Storage e chiusura con svuotamento della sessione. Le richieste HTTPS sono intercettate e servite con HTML sintetico: **nessuna ricerca o richiesta di cancellazione reale viene eseguita dal collaudo**. Il profilo e le catture rimangono nella cartella ignorata `.desktop-work/workflow-smoke-<id>/`.

Anche il collaudo nativo precedente (`scripts/smoke-desktop.py`) riesce attraverso **Apri archivio precedente**, comprendendo sblocco, elenco/dettaglio, revisione, backup approvato, zoom 200% e blocco della navigazione esterna nel bridge privilegiato.

È stato inoltre compilato un nuovo installer locale non firmato, versione invariata 0.1.0.dev0. Il bundle supera `smoke-desktop.py --executable`: avvio del percorso principale, apertura dell’archivio precedente, revisione, backup, layout 1920/640 e isolamento della navigazione. La coda browser completa è collaudata nativamente dalla sorgente, non dal bundle. Inventario: 210 file e 20 distribuzioni Python. Nessuna installazione personale o pubblicazione effettuata.

Limiti attuali: nessun adattatore broker reale qualificato; le schede distribuite restano manuali. Gli automatismi sono provati su contratti sintetici. GitHub e Wikipedia limitano la ricerca ai propri contenuti pubblici; non sono una scansione del Web. DuckDuckGo rimane un collegamento esterno a causa della policy di incorporamento. I risultati locali non qualificano provider reali, accessibilità assistiva o installazione su macchina pulita.

## Collaudo precedente dell’interfaccia avanzata

## Risultati osservati

Ambiente: Windows 11 x64, Python 3.13.17, WebView2 installato. Dati sintetici e server locali; nessun provider reale contattato per le prove operative.

| Verifica | Esito |
|---|---|
| Suite Python con extra demo e Chromium | 52 test riusciti, inclusi 11 test desktop |
| Ambiente di packaging senza extra demo | 52 test, 47 eseguiti e 5 demo saltati esplicitamente |
| Frontend TypeScript + Vite | Build riuscita |
| Test frontend | 3 riusciti |
| npm audit | Nessuna vulnerabilità segnalata |
| pip check e CLI isolata | Riusciti |
| Launcher PowerShell 5.1 e 7 | 68 varianti per interprete, riuscite |
| Test nativo della sorgente | Apertura, elenco/dettaglio, revisione e backup approvato tramite bridge reale riusciti |
| Test del bundle PyInstaller | Stesso percorso principale riuscito dall’eseguibile, con profilo locale isolato |
| Input HTML ostile | Mostrato come testo, senza esecuzione |
| Archivio bloccato | Riscontri rimossi dalla UI; approvazioni precedenti invalidate |
| Navigazione esterna nel WebView | Bloccata; bridge ancora utilizzabile dopo il tentativo |
| Layout | Catture reali WebView2, finestra 1280×720 e viewport 1920/640; nessuno scorrimento orizzontale rilevato |
| Zoom 200% | WebView2 ZoomFactor=2; viewport 640 CSS px, contenuto 632 CSS px, cattura nativa senza il ritaglio di CDP |
| Revisione UX indipendente | Corretti focus/visibilità dei moduli e transizioni elenco/dettaglio; verifica mirata delle correzioni approvata |
| Setup Inno Setup 6 | Compilato, senza firma; inventario e checksum generati |

Gli screenshot e i risultati integrali sono locali e ignorati da Git, in `.impeccable/review/` e `.desktop-work/`. La prova del bundle usa esclusivamente dati sintetici e un percorso dati isolato. Il debug remoto è attivato dal test, non dal codice dell’app distribuita.

Per ripetere: build frontend, poi `python scripts/smoke-desktop.py` in un ambiente con gli extra desktop e demo. Per il bundle: `python scripts/smoke-desktop.py --executable PERCORSO_COMPLETO_EXE`. Il test non installa né disinstalla il prodotto.

## Limiti e criteri ancora aperti

- Installer non firmato: manca il certificato Authenticode. Nessuna pubblicazione effettuata.
- Installazione, aggiornamento e disinstallazione non collaudati su macchina pulita o con WebView2 assente. Non è stata modificata l’installazione personale del sistema.
- Collegamento e installazione del bootstrapper WebView2 predisposti nello script, non eseguiti durante questo collaudo.
- Narrator e interazione in contrasto elevato restano da verificare manualmente. La presenza di markup semantico e regole CSS non costituisce una certificazione di accessibilità.
- Blocco per inattività coperto da test; hook SessionSwitch predisposto, ma nessun blocco della sessione Windows dell’utente è stato provocato.
- Il test nativo percorre il flusso principale, non tutte le combinazioni di ogni operazione. Le altre operazioni usano i servizi sottoposti alla suite Python.
- Prestazioni con archivi di migliaia di elementi, qualificazione dei provider reali e pubblicazione della CI aggiornata restano da verificare.

TASK-009 e TASK-010 ricevono queste evidenze e restano aperti per i rispettivi criteri residui. La versione resta 0.1.0.dev0.
