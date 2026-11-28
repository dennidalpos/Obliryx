# Obliryx desktop Windows

## Uso

L’ingresso principale è ora un percorso in cinque fasi:

1. Inserisci almeno email, telefono, nome e cognome o username. Città facoltativa.
2. Avvia l’analisi. Gli identificativi sono comunicati alle fonti dichiarate: GitHub per email/nome/username e Wikipedia italiana per gli identificativi inseriti. Le ricerche sono gratuite e senza chiavi personali. I candidati vengono verificati nel testo visibile delle pagine; gli snippet non sono prove.
3. Seleziona più presenze o procedure broker. Le due categorie restano separate. Le fonti non disponibili e le ricerche limitate vengono indicate nella copertura.
4. Controlla e approva un solo riepilogo con destinazioni, effetti e dati trasmessi. Modificare la selezione invalida il riepilogo precedente. La validità è di cinque minuti e ogni approvazione è utilizzabile una sola volta.
5. L’app esegue prima le procedure automatiche qualificate e poi mostra le verifiche assistite. Completa CAPTCHA o codici nel browser integrato e torna all’app per Continua, Salta o Annulla. Per canali email vengono preparate bozze senza invio automatico. Gli opt-out del browser hanno link per il browser abituale, poiché un cookie nel browser temporaneo dell’app non protegge gli altri browser.

**Copertura attuale:** GitHub cerca solo profili pubblici, Wikipedia solo i contenuti dell’enciclopedia italiana. Le API possono rispondere con limiti o errori; non sono sostituite con servizi a pagamento. Massimo cinque candidati per ricerca e venti pagine per analisi. DuckDuckGo non viene incorporato: la [policy ufficiale](https://duckduckgo.com/acceptable-use) vieta tale uso; l’app offre collegamenti esterni senza interrogare automaticamente quel servizio. Non è una scansione universale dei dati o dei database privati dei broker.

Riferimenti delle interfacce gratuite: [GitHub, ricerca utenti pubblici e limiti senza autenticazione](https://docs.github.com/en/rest/search/search#search-users), [MediaWiki, ricerca](https://www.mediawiki.org/wiki/API:Search), [MediaWiki, regole di utilizzo](https://www.mediawiki.org/wiki/API:Etiquette). L’app usa richieste GET limitate, un User-Agent identificabile e nessun token personale.

**Procedure reali:** le dieci schede distribuite sono manuali. Nessun adattatore broker reale è abilitato all’invio automatico. Gli automatismi e la ripresa dopo verifica sono provati con contratti sintetici; una procedura reale richiede qualificazione separata. Cambi di destinazione, campi o contratto invalidano l’automazione. Errori dopo la prenotazione restano incerti e non vengono ritentati automaticamente.

Lo storico principale viene creato automaticamente in `%LOCALAPPDATA%\obliryx\desktop-history.sqlite3`, con credenziale casuale protetta per l’utente corrente in `desktop-key.dpapi`. **Non serve una password aggiuntiva.** Per il recupero sono necessari database, credenziale DPAPI e account Windows che può decifrarla; la sola copia del database non è un backup portabile. Il registro degli invii rimane separato. In assenza della credenziale l’app non ricrea o sovrascrive lo storico. Nessuna esportazione automatica degli identificativi.

Il browser integrato è una finestra nativa dell’app con dominio visibile e pulsante Torna all’app. Usa un ambiente separato e InPrivate, senza bridge Python, oggetti host, messaggi Web, download o permessi dispositivo. Le cartelle del runtime rimangono locali e non vengono eliminate automaticamente. Chiudi sessione interrompe le nuove operazioni, svuota dati e approvazioni in memoria e nasconde le pagine; un invio già iniziato può terminare.

### Archivi precedenti e operazioni avanzate

**Apri archivio precedente** accede facoltativamente all’interfaccia precedente. Questi archivi conservano la propria passphrase; non vengono migrati, cancellati o aperti con la nuova credenziale Windows. Il pulsante **Torna alla ricerca Web** chiude la sessione precedente. I comandi CLI continuano a funzionare come documentato nel README.

Il setup di sviluppo si trova in `dist/windows-<build>/installer/Obliryx-0.1.0.dev0-windows-x64-setup.exe` dopo la build. `dist/latest-desktop.json` indica il risultato più recente. Ogni build conserva una cartella distinta. Destinazione: Windows 11 x64. Python, Node e Git non servono sul dispositivo dell’utente. WebView2 Evergreen deve essere disponibile.

Il setup installa per utente in `%LOCALAPPDATA%\Programs\Obliryx`. Avvia dal menu Start per il percorso guidato. Solo nell’interfaccia degli archivi precedenti crea un archivio oppure apri un file esistente e inserisci una passphrase di almeno 12 caratteri. La perdita di quella passphrase impedisce l’accesso all’archivio precedente.

In **Importa e monitora**, scegli EML/MBOX, trascina un file o collega IMAP in sola lettura. In **Riscontri**, seleziona una riga e segui il prossimo passo. **Altre azioni** rende disponibili tutti i percorsi sul riscontro. Gli invii sono individuali: verifica l’anteprima e digita CONFERMO per ogni approvazione. Un esito incerto non viene ritentato automaticamente.

**Ricerche** distingue confronto locale, pagina Web, Brave e HIBP. Le credenziali vengono richieste al momento; i risultati Brave sono transitori. Il catalogo broker descrive procedure manuali e non prova il possesso dei tuoi dati.

Il blocco chiude l’archivio e invalida le approvazioni. Un POST già iniziato può terminare; annullare non lo richiama. Il monitoraggio EML termina con la sessione. Per consultare i risultati durante un monitoraggio, arrestalo prima.

## Build

Prerequisiti di sviluppo: Python 3.13 x64, Node 22 LTS con npm, Inno Setup 6. Dalla radice:

```powershell
.\scripts\build-desktop.ps1 -Python python
```

Le dipendenze Python sono bloccate in `packaging/requirements-windows.lock`; quelle JavaScript in `frontend/package-lock.json`. Gli ambienti nuovi sono in `.desktop-work/`, gli artefatti in `dist/`. Il frontend viene incorporato nel bundle PyInstaller, senza CDN. La CLI continua a essere installabile separatamente.

Per includere il bootstrapper WebView2 scaricalo dal sito Microsoft e passa `-WebViewBootstrapper PERCORSO`. Lo script ne verifica la firma Microsoft. Senza bootstrapper il setup indica dove ottenere anche l’installer Evergreen Standalone offline e si arresta se il runtime manca. Non viene installato un runtime senza conferma.

Per una release pubblica passa `-PublicRelease -SignTool PERCORSO -CertificateThumbprint IMPRONTA`. La chiave privata deve essere già nel gestore certificati; non copiarla nel repository. Lo script firma eseguibile, installer e disinstallatore e verifica le firme finali. In assenza di certificato si produce soltanto una build locale di sviluppo.

La build genera inventario, licenze e SHA256SUMS. Prima della pubblicazione esaminare working tree, indice, storia rilevante, wheel, sorgenti e bundle per dati personali e segreti; confrontare anche l’inventario con i contenuti effettivamente distribuiti. Pubblicazione e scelta di una versione di rilascio richiedono autorizzazioni separate.

## Aggiornamento e recupero

Chiudi l’app, conserva un backup cifrato e installa la nuova versione sopra la precedente. Non cancellare `action-state`. Il setup aggiorna i binari; la disinstallazione conserva dati, registro invii e copie. Non esiste aggiornamento automatico.

Il rollback consiste nel reinstallare i binari precedenti compatibili con lo schema. Questa UI non introduce una migrazione del database. Un rollback del database richiede ripristino in un nuovo file e controllo del registro: non sostituire o rimuovere il registro per riabilitare gli invii.

Se WebView2 non parte, installa o ripara il runtime ufficiale e ripeti l’avvio. Se il file di destinazione esiste, usa Apri esistente o un nuovo nome: la creazione non sovrascrive. Se un’operazione viene interrotta, gli elementi importati restano conservati. Dopo errori di invio consulta il registro prima di ripetere qualsiasi azione.

## Qualificazione della distribuzione

La CI distingue test base, demo Chromium e build desktop. I test Python del bridge non provano il rendering nativo. Prima della distribuzione a utenti comuni verificare su macchina pulita: utente standard senza Python, runtime presente/assente, rete assente, percorsi Unicode, aggiornamento, disinstallazione e conservazione del registro. Verificare inoltre Narrator, tastiera, contrasto elevato, DPI e zoom 200%.

La firma non è stata predisposta dal progetto. Il collaudo su un ambiente di sviluppo non sostituisce la matrice su macchina pulita. Vedi `docs/desktop-validation.md` per i risultati osservati di questa implementazione.
