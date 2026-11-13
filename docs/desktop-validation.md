# Verifiche desktop — 13 novembre 2026

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
