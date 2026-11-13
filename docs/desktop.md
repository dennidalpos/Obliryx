# Obliryx desktop Windows

## Uso

Il setup di sviluppo si trova in `dist/windows-<build>/installer/Obliryx-0.1.0.dev0-windows-x64-setup.exe` dopo la build. `dist/latest-desktop.json` indica il risultato più recente. Ogni build conserva una cartella distinta. Destinazione: Windows 11 x64. Python, Node e Git non servono sul dispositivo dell’utente. WebView2 Evergreen deve essere disponibile.

Il setup installa per utente in `%LOCALAPPDATA%\Programs\Obliryx`. Avvia dal menu Start, crea un archivio oppure apri un file esistente e inserisci una passphrase di almeno 12 caratteri. La perdita della passphrase impedisce l’accesso. L’app non la recupera né la memorizza.

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
