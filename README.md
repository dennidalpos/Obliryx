# Obliryx

Obliryx raccoglie in un archivio personale i riscontri di mailing list, marketing ed esposizione dei propri dati. Analizza messaggi `.eml` ed esportazioni `.mbox` della propria posta e consente di aggiungere riscontri Web con la relativa fonte. I messaggi originali restano nei file di partenza. L’archivio SQLite cifra riscontri, URL di disiscrizione e anteprime approvate. Nei nuovi archivi una chiave derivata dalla passphrase protegge le chiavi dei dati e delle impronte.

## Percorso desktop: ricerca Web e interventi

L’app Windows si apre direttamente sull’inserimento di email, telefono, nome e cognome o username, con città facoltativa. Non richiede di importare la posta, creare un archivio o scegliere una password: lo storico cifrato è aperto con una credenziale casuale protetta per l’account Windows tramite DPAPI. La CLI conserva le proprie funzioni e la passphrase degli archivi precedenti.

Il percorso ha cinque fasi: **dati → analisi → selezione → riepilogo approvato → interventi**. Le ricerche automatiche gratuite riguardano i profili pubblici GitHub (email, nome, username) e Wikipedia italiana (identificativi inseriti). Nessuna chiave API, abbonamento o ricerca della posta. Gli identificativi cercati vengono comunicati a queste fonti dopo l’avvio dell’analisi; non vengono salvati come campi di ricerca. Sono consultati al massimo cinque candidati per ricerca e venti pagine per sessione. Una corrispondenza viene segnalata soltanto dopo il confronto con il testo visibile della pagina nel browser integrato, separato dal bridge dell’app.

Queste fonti hanno una copertura limitata ai propri contenuti: **non costituiscono una scansione dell’intero Web o dei database privati dei broker**. DuckDuckGo è disponibile tramite link nel browser esterno: la sua [acceptable use policy](https://duckduckgo.com/acceptable-use) vieta l’incorporamento del servizio. La disponibilità delle fonti e le ricerche incomplete sono mostrate esplicitamente.

L’elenco separa le presenze osservate dalle procedure broker senza possesso accertato. L’approvazione unica lega il lotto alle destinazioni e ai dati mostrati. Il motore esegue prima gli adattatori automatici qualificati, poi accoda verifiche assistite nel browser integrato. **Il catalogo distribuito contiene attualmente procedure manuali: nessun broker reale è dichiarato automatizzato o qualificato.** Il flusso automatico è collaudato esclusivamente con procedure sintetiche. Restano disponibili fonti ufficiali, link diretti e bozze email; gli opt-out basati su cookie vanno eseguiti nel browser abituale e non equivalgono alla cancellazione dei dati.

Vedi [uso e limiti del percorso guidato](docs/desktop.md). I precedenti archivi si aprono facoltativamente da **Apri archivio precedente**; non vengono migrati o sovrascritti.

## Avvio locale

È disponibile anche il progetto dell’**app desktop Windows**, con interfaccia React incorporata, archivio locale e conferme individuali. Per creare l’installer di sviluppo: `scripts/build-desktop.ps1` (Python 3.13 x64, Node 22 LTS, Inno Setup 6). Il dispositivo dell’utente non richiede Python. Vedi [guida desktop e distribuzione](docs/desktop.md), [copertura delle funzioni](docs/desktop-coverage.md) e [verifiche e limiti](docs/desktop-validation.md). La build di sviluppo non firmata non è una release pubblica qualificata.

Su Windows puoi usare il menu PowerShell dalla cartella del progetto:

```powershell
.\Avvia-Obliryx.ps1
```

Il menu guida importazione, ricerche, revisione dei riscontri, bozze e disiscrizioni. Da **Archivio e ambiente Python** puoi anche gestire il registro invii, le copie e la passphrase. Se l'ambiente Python manca, il launcher propone di creare `.venv` e installare le dipendenze. Passphrase, chiavi API e credenziali vengono richieste direttamente da Obliryx durante l'operazione. Usa `0` per tornare indietro e `q` per annullare l'inserimento di un parametro.

Puoi scegliere un archivio per la sessione dal menu o con `-DatabasePath "D:\Dati personali\obliryx.sqlite3"`. Il parametro `-PythonPath` permette di usare il percorso di un interprete Python già configurato. Il launcher funziona con Windows PowerShell 5.1 e PowerShell 7.

Serve Python 3.11 o successivo. Da PowerShell, nella cartella del progetto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m obliryx --help
```

Su Linux e macOS, usa `.venv/bin/python` al posto di `.\.venv\Scripts\python.exe`. L’archivio viene creato sotto `%LOCALAPPDATA%\obliryx` su Windows e sotto `~/.local/share/obliryx` negli altri ambienti. Per scegliere un archivio diverso, metti `--db PERCORSO` prima del comando. Usa una passphrase lunga e unica. La perdita della passphrase comporta la perdita dell’accesso ai riscontri. Il file contiene metadati operativi, fra cui date e stati delle azioni. Le esportazioni originali, il terminale e le copie di backup richiedono la stessa attenzione dell’archivio.

## Flusso di lavoro

| Comando | Operazione |
|---|---|
| `obliryx import-eml PERCORSO` | Analizza offline un `.eml` o una cartella di `.eml`. Estrae segnali di lista e candidati alla disiscrizione da intestazioni e collegamenti HTML riconoscibili. |
| `obliryx import-mbox ESPORTAZIONE.mbox` | Analizza offline un’intera esportazione. Il riepilogo distingue nuovi riscontri, duplicati, messaggi senza indicatori ed errori. |
| `obliryx import-imap SERVER --limit 50` | Analizza i messaggi recenti della tua cartella IMAP in sola lettura. `--match documento` confronta il valore esclusivamente sul dispositivo. |
| `obliryx watch-eml CARTELLA --interval 30` | Importa i file `.eml` nuovi o aggiornati quando la cartella resta sotto monitoraggio. Premi `Ctrl+C` per fermarlo. |
| `obliryx scan-mail ESPORTAZIONE.mbox documento` | Cerca un tuo dato nell’oggetto e nel testo analizzabile delle email. Funziona anche su `.eml` e cartelle di `.eml`. Chiede il valore senza mostrarlo a terminale. |
| `obliryx record` | Registra organizzazione, fonte Web, tipi di dati osservati, eventuale prova di acquisto e procedura individuata. |
| `obliryx search-web` | Interroga Brave per un proprio identificativo. Mostra risultati transitori da verificare alla fonte. Richiede una chiave Brave Search API. |
| `obliryx check-page email` | Cerca localmente un proprio dato nel testo HTML restituito dalla pagina HTTPS approvata. Registra il riscontro se trova una corrispondenza e segnala eventuali link candidati. Il valore cercato resta sul dispositivo. |
| `obliryx recheck-page ID` | Ricontrolla lo stesso dato sulla pagina del riscontro e aggiunge un esito datato. Chiede di reinserire il valore prima di contattare la fonte. |
| `obliryx check-breach --method diretto` | Verifica una propria email via [Have I Been Pwned](https://haveibeenpwned.com/) e registra le corrispondenze. `--method prefisso` invia un prefisso hash e richiede un piano che supporti questa funzione. |
| `obliryx list` | Elenca organizzazioni dichiarate, gravità, stato dell’iscrizione e numero di canali. |
| `obliryx campaigns` | Raggruppa i messaggi per mittente e lista dichiarati. Evidenzia gravità, iscrizioni non riconosciute e messaggi privi di un canale individuato. |
| `obliryx show ID` | Mostra evidenze, collegamenti completi e storico delle azioni. |
| `obliryx review ID non_riconosciuta` | Registra che l’utente non riconosce l’iscrizione. Il messaggio da solo non dimostra un acquisto di dati o l’assenza di consenso. |
| `obliryx outcome ID dato_non_osservato` | Aggiunge un esito dichiarato dall’utente allo storico, separato dagli esiti tecnici di invio. |
| `obliryx document ID` | Aggiunge o aggiorna le prove, le categorie osservate e il contatto email ufficiale. |
| `obliryx identify ID` | Cerca la denominazione del titolare in una pagina informativa approvata. Dopo la tua verifica, aggiunge al riscontro nome, fonte e motivo del collegamento, mantenendo il mittente dichiarato. |
| `obliryx draft ID` | Genera una bozza di opposizione, cancellazione o accesso. `--route N` usa oggetto e testo dichiarati dal canale email. `--compose` apre la bozza nel client di posta con il destinatario approvato. L’invio finale resta nel client. |
| `obliryx find-routes ID` | Consulta una pagina informativa HTTPS approvata, senza parametri personali, e allega alla pratica i link candidati con la pagina di provenienza. I link trovati non vengono visitati in automatico. |
| `obliryx confirm-route ID N` | Registra che hai verificato manualmente la pertinenza di un candidato Web alla disiscrizione, anche se proviene da un’email. La conferma non lo abilita al one-click. |
| `obliryx open-route ID N` | Mostra il canale HTTPS e lo apre nel browser dopo la conferma. Il sito può ricevere subito un identificativo o disiscrivere l’utente. |
| `obliryx form-unsubscribe ID N` | Su un canale Web verificato, legge un modulo semplice, inserisce la tua email e mostra destinazione e campi. Il POST richiede una conferma distinta dalla consultazione. |
| `obliryx unsubscribe ID ORIGINALE` | Cerca il messaggio nel file `.eml` o `.mbox` originale. Verifica la firma DKIM e il destinatario prima di chiedere conferma per il POST one-click. |
| `obliryx unsubscribe-imap ID` | Recupera l’originale dalla fonte IMAP registrata e avvia le stesse verifiche one-click. Il recupero e l’invio hanno conferme distinte. |

Verifica il mittente e la destinazione prima di aprire un canale. Per una richiesta sospetta, trova il contatto ufficiale indipendentemente dal messaggio. Il percorso automatico richiede che DKIM copra le intestazioni di disiscrizione e il mittente e destinatario univoci. Obliryx usa l’indirizzo IP validato per la connessione HTTPS, senza cookie e senza seguire redirect. Un esito `accepted` indica che il sito ha accettato il POST. Un timeout resta `delivery_unknown` e un nuovo tentativo sulla stessa destinazione viene bloccato. [RFC 2369](https://www.rfc-editor.org/rfc/rfc2369.html) · [RFC 8058](https://www.rfc-editor.org/rfc/rfc8058.html)

Usa esportazioni MBOX con separatori `From ` e messaggi fino a 5 MiB. Le revisioni già presenti sono conservate quando una seconda esportazione contiene lo stesso messaggio con terminatori di riga diversi. Alcune esportazioni riscrivono il corpo o le intestazioni. Se la firma diventa non verificabile, usa il messaggio originale o passa al flusso assistito. Il raggruppamento di `campaigns` usa le intestazioni dichiarate e va trattato come punto di partenza per la verifica del soggetto. [RFC 4155](https://www.rfc-editor.org/rfc/rfc4155.html)

`scan-mail` confronta letteralmente il valore dopo aver normalizzato maiuscole, Unicode e spazi. Cerca nell’oggetto e nei primi 200.000 caratteri di ciascuna parte testuale supportata. Esclude intestazioni dei destinatari, allegati, script e stili. Nel riscontro aggiunge categoria e posizione, senza aggiungere estratti del testo o salvare il valore di ricerca come campo. Omette l’oggetto se contiene la corrispondenza. Una corrispondenza attesta la presenza nel messaggio analizzato. Il contenuto può provenire da citazioni, inoltri o firme, quindi la verifica del contesto resta necessaria.

`form-unsubscribe` supporta un modulo HTML statico con un campo email, un pulsante di disiscrizione riconoscibile ed eventuali campi nascosti. Dopo l’approvazione rilegge il modulo con la stessa destinazione di rete. Se la destinazione, il pulsante o i campi sono cambiati, chiede di ripartire da una nuova anteprima. Invia un POST HTTPS alla stessa origine e non esegue script, invia cookie o segue redirect. Usa il browser per flussi con login, CAPTCHA, JavaScript, campi aggiuntivi o passaggi multipli. L’esito tecnico dell’invio è registrato separatamente dalla rimozione, che puoi annotare con `outcome`. Il flusso è stato verificato su un server HTTPS locale di prova. [HTML Standard, invio dei moduli](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#form-submission-algorithm)

Dopo una richiesta, usa `recheck-page` per osservare di nuovo la fonte. `dato_non_osservato` vale per il testo accessibile della pagina in quel momento. Errori e schermate di accesso vengono registrati come `non_verificabile`. `ricomparsa` indica che il dato è stato visto di nuovo dopo un controllo valido in cui era assente. `show` espone lo storico dei ricontrolli e `list` mostra l’ultimo esito. Le risposte del titolare rimangono registrabili con `outcome`.

Usa il nome del server IMAP indicato dal tuo provider. Obliryx verifica il certificato TLS sulla porta 993 e apre `INBOX` o la cartella ASCII indicata con `--mailbox` in sola lettura. Legge fino a 500 messaggi recenti per sessione e salta quelli oltre 5 MiB. Inserisci una password per app oppure, con `--auth xoauth2`, un token IMAP già ottenuto dal provider. Le credenziali restano in memoria per la sessione. I loro permessi dipendono dal provider. Per esempio, Gmail richiede lo scope `https://mail.google.com/` per IMAP. Obliryx conserva nel riscontro un riferimento IMAP cifrato per ritrovare il messaggio. Se l’identità della cartella cambia o il messaggio non corrisponde al riscontro, il one-click si interrompe. La modalità è stata collaudata su un server IMAP TLS locale. [RFC 9051](https://www.rfc-editor.org/rfc/rfc9051.html) · [Gmail, XOAUTH2](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol)

## Catalogo broker per Italia e UE

`obliryx broker-catalog` elenca le procedure e `obliryx broker-catalog liveramp-accesso-it` mostra una scheda. La consultazione è locale e funziona senza sbloccare un archivio. La prima versione contiene dieci procedure manuali di accesso o opt-out pubblicitario. Le schede includono il paese o l’area di applicabilità, il titolare, la fonte ufficiale, il canale, i dati previsti e l’effetto dichiarato. La presenza nel catalogo lascia `holding_state` a `unknown`. I destinatari e gli effetti dipendono dalla procedura scelta, per esempio contatto privacy per i residenti in Italia o preferenza pubblicitaria del singolo browser. [LiveRamp, contatti privacy](https://liveramp.com/privacy) · [Adform, opt-out](https://site.adform.com/privacy-center/platform-privacy/opt-out/)

Il file `obliryx/broker_procedures.json` distribuisce schede originali sotto licenza MIT. Ogni scheda rimanda alla pagina del titolare e riporta la data della revisione documentale. Se cambiano destinatario, campi o effetto, verifica nuovamente la fonte e aggiorna versione, data e `review_sha256` con `review_fingerprint` da `obliryx.broker_catalog`. Una scheda modificata con la vecchia impronta viene rifiutata. Usa i canali indicati manualmente dopo aver verificato la pertinenza della procedura.

### Adattatore multistep di prova

`obliryx multistep-demo --port PORTA --ca CA.pem` usa il protocollo dimostrativo `obliryx-demo-v1` sul sito HTTPS locale. Verifica il certificato con la CA di prova fornita e chiede conferme distinte per aprire la sessione, preparare la richiesta sintetica e confermarla. Cookie e token rimangono in memoria e il cookie viene inviato solo al sito locale. Chromium, in un contesto temporaneo offline, ispeziona HTML inerte per controllare i due moduli previsti. Il flusso si ferma se il contratto cambia o se il sito richiede un passaggio assistito, come CAPTCHA, accesso o documenti. I broker del catalogo mantengono i loro canali manuali.

Per riprodurre il collaudo con Chromium e il server HTTPS sintetico avviato dai test:

```powershell
python -m pip install -e ".[demo]"
python -m playwright install chromium
python -m unittest discover -s tests -p "test_multistep_demo.py" -v
```

## Archivio, copie e recupero

| Comando | Operazione |
|---|---|
| `obliryx backup COPIA.sqlite3` | Crea una copia coerente di SQLite con gli stessi dati cifrati e la stessa passphrase dell’archivio al momento della copia. |
| `obliryx --db COPIA.sqlite3 restore NUOVO.sqlite3` | Sblocca la copia con la sua passphrase e ripristina in un file nuovo. Poi seleziona `NUOVO.sqlite3` con `--db` o dal menu. |
| `obliryx export RIEPILOGO.json` | Esporta in chiaro identificativi dei riscontri, mittente o organizzazione, categorie, stati, esiti e storico tecnico. Il riepilogo omette URL, note libere, credenziali e dati delle anteprime. |
| `obliryx rotate-passphrase` | Richiede la passphrase corrente e due inserimenti della nuova. Cambia la protezione delle chiavi esistenti, preservando la lettura dei record e le deduplicazioni. |
| `obliryx action-status` | Mostra se gli invii sono sospesi, il percorso del registro separato e gli esiti incerti o da riconciliare. |
| `obliryx action-reconcile` | Dopo la verifica manuale, riallinea archivio e registro e recupera gli esiti per i riscontri ancora presenti. Le destinazioni già registrate restano bloccate, inclusi gli esiti incerti. |
| `obliryx action-pause` / `obliryx action-resume` | Sospende nuove prenotazioni POST e invalida le anteprime in corso. La riattivazione richiede conferma e ogni nuovo invio parte da una nuova anteprima. Un POST già prenotato può essere in corso. |

Backup, ripristino ed esportazione richiedono conferma del percorso e usano solo destinazioni nuove in cartelle già esistenti. Il registro invii è sotto `action-state` nella cartella dati predefinita dell’utente, anche con `--db`. La copia dell’archivio esclude questo registro. Obliryx registra l’approvazione cifrata e riserva la destinazione prima del POST, con una transazione SQLite tra archivio e registro. Un’interruzione prima della risposta lascia un esito incerto. La protezione vale per le disiscrizioni POST eseguite da Obliryx. L’apertura di un link nel browser e l’invio dal client di posta hanno conferme separate. [SQLite, transazioni su database allegati](https://www.sqlite.org/lang_attach.html)

Prima di usare un archivio ripristinato, esegui `action-status`. Se il registro manca o diverge, confronta i tentativi disponibili con ricevute e riscontri alla fonte prima di confermare `action-reconcile`. Lo stesso controllo serve al primo uso degli invii su archivi creati con versioni precedenti. Quando manca il registro, il programma dispone soltanto dello storico presente nella copia e la verifica manuale deve coprire anche gli invii successivi. Conserva il registro attuale sul dispositivo e usa una sola copia dell’archivio per il lavoro corrente. La protezione presuppone che il sistema e il registro locale siano affidabili. Ripristinare insieme archivio e registro da copie coordinate ma obsolete può rendere invisibili gli invii più recenti.

### Accesso ai file e retention

- Tieni archivio, registro, copie ed esportazioni in cartelle private e usa la cifratura del volume per i supporti rimovibili. Su Windows i file ereditano le autorizzazioni della cartella. Controllale nelle proprietà di sicurezza prima di esportare. Su Unix i nuovi file sono creati con permessi al massimo `0600`.
- I file SQLite conservano in chiaro metadati operativi come date, stati e identificativi interni. Il terminale può mostrare destinatari, URL e campi durante le anteprime. Proteggi sessioni e trascrizioni. La cifratura dei record presuppone una passphrase robusta e un host affidabile durante lo sblocco.
- Le copie esistenti continuano ad aprirsi con la passphrase che avevano quando sono state create. La rotazione cambia la passphrase del file corrente e conserva le chiavi dei dati. Se qualcuno ha ottenuto quelle chiavi da una copia precedente, la rotazione della sola passphrase non le sostituisce.
- Definisci per quanto tempo tenere ogni backup ed export. Prima di rimuoverli, chiudi Obliryx, inventaria i percorsi e le copie sincronizzate, controlla gli hash e verifica almeno un ripristino delle copie che vuoi conservare. Conferma esplicitamente i file da eliminare prima di rimuoverli con gli strumenti del sistema operativo.
- Per dismettere l’intero archivio, sospendi i POST e includi nell’inventario archivio, copie, esportazioni e file temporanei correlati. Conserva il registro invii finché una copia può essere riaperta. Rimuovilo solo dopo aver confermato la dismissione di tutte le copie. Gestisci separatamente file originali, cestino, versioni cloud e richieste presso i provider. La rimozione di un file dal filesystem lascia la cancellazione fisica al supporto e alle sue politiche di retention.

## Stato di sviluppo

La ricerca Web mostra candidati. Usa `record` solo dopo aver verificato indipendentemente il riscontro alla fonte. I risultati del motore non vengono scritti nell’archivio e le chiavi dei provider vengono richieste a ogni uso. HIBP riporta associazioni con raccolte note al provider. Le categorie riportate per l’intero incidente non provano che ogni categoria fosse presente nel tuo record. [Brave, termini dell’API](https://api-dashboard.search.brave.com/documentation/resources/terms-of-service) · [Have I Been Pwned, documentazione e attribuzione](https://haveibeenpwned.com/API/v3)

`check-page` controlla una pagina per volta e usa il testo disponibile nel documento HTML. Contenuti dinamici, accessi protetti e redirect richiedono verifica manuale. I link individuati restano candidati da controllare. Il monitoraggio continuo lavora sulla cartella `.eml` scelta durante la sessione. L’accesso IMAP avviene su richiesta e l’autenticazione disponibile dipende dal provider. Il flusso one-click è collaudato con simulazioni e messaggi sintetici firmati.

Codice distribuito con [licenza MIT](LICENSE).

Il workflow GitHub Actions verifica installazione e test con Python 3.11 e 3.15 su Windows, Linux e macOS. Il primo collaudo pubblico ha superato 27 test su ciascuna delle sei combinazioni. I test usano dati sintetici e server di prova locali per IMAP e disiscrizioni. [Esito CI del primo commit](https://github.com/dennidalpos/Obliryx/actions/runs/43268081275)

Per eseguire le prove locali dopo l’installazione:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
