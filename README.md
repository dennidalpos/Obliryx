# Obliryx

Obliryx raccoglie in un archivio personale i riscontri di mailing list, marketing ed esposizione dei propri dati. Analizza messaggi `.eml` ed esportazioni `.mbox` della propria posta e consente di aggiungere riscontri Web con la relativa fonte. I messaggi originali restano nei file di partenza. L’archivio SQLite cifra il contenuto dei riscontri, inclusi gli URL di disiscrizione, con una chiave derivata dalla passphrase.

## Avvio locale

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

`form-unsubscribe` supporta un modulo HTML statico con un campo email, un pulsante di disiscrizione riconoscibile ed eventuali campi nascosti. Invia un POST HTTPS alla stessa origine e non esegue script, invia cookie o segue redirect. Usa il browser per flussi con login, CAPTCHA, JavaScript, campi aggiuntivi o passaggi multipli. L’esito tecnico dell’invio è registrato separatamente dalla rimozione, che puoi annotare con `outcome`. Il flusso è stato verificato su un server HTTPS locale di prova. [HTML Standard, invio dei moduli](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#form-submission-algorithm)

Dopo una richiesta, usa `recheck-page` per osservare di nuovo la fonte. `dato_non_osservato` vale per il testo accessibile della pagina in quel momento. Errori e schermate di accesso vengono registrati come `non_verificabile`. `ricomparsa` indica che il dato è stato visto di nuovo dopo un controllo valido in cui era assente. `show` espone lo storico dei ricontrolli e `list` mostra l’ultimo esito. Le risposte del titolare rimangono registrabili con `outcome`.

Usa il nome del server IMAP indicato dal tuo provider. Obliryx verifica il certificato TLS sulla porta 993 e apre `INBOX` o la cartella ASCII indicata con `--mailbox` in sola lettura. Legge fino a 500 messaggi recenti per sessione e salta quelli oltre 5 MiB. Inserisci una password per app oppure, con `--auth xoauth2`, un token IMAP già ottenuto dal provider. Le credenziali restano in memoria per la sessione. I loro permessi dipendono dal provider. Per esempio, Gmail richiede lo scope `https://mail.google.com/` per IMAP. Obliryx conserva nel riscontro un riferimento IMAP cifrato per ritrovare il messaggio. Se l’identità della cartella cambia o il messaggio non corrisponde al riscontro, il one-click si interrompe. La modalità è stata collaudata su un server IMAP TLS locale. [RFC 9051](https://www.rfc-editor.org/rfc/rfc9051.html) · [Gmail, XOAUTH2](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol)

## Stato di sviluppo

La ricerca Web mostra candidati. Usa `record` solo dopo aver verificato indipendentemente il riscontro alla fonte. I risultati del motore non vengono scritti nell’archivio e le chiavi dei provider vengono richieste a ogni uso. HIBP riporta associazioni con raccolte note al provider. Le categorie riportate per l’intero incidente non provano che ogni categoria fosse presente nel tuo record. [Brave, termini dell’API](https://api-dashboard.search.brave.com/documentation/resources/terms-of-service) · [Have I Been Pwned, documentazione e attribuzione](https://haveibeenpwned.com/API/v3)

`check-page` controlla una pagina per volta e usa il testo disponibile nel documento HTML. Contenuti dinamici, accessi protetti e redirect richiedono verifica manuale. I link individuati restano candidati da controllare. Il monitoraggio continuo lavora sulla cartella `.eml` scelta durante la sessione. L’accesso IMAP avviene su richiesta e l’autenticazione disponibile dipende dal provider. Il flusso one-click è collaudato con simulazioni e messaggi sintetici firmati. Prima di un ripristino riconcilia le azioni successive alla copia. Una copia precedente può aver perso la registrazione di un invio già eseguito.

Codice distribuito con [licenza MIT](LICENSE).

Il workflow GitHub Actions è configurato per verificare installazione e test con Python 3.11 e 3.15 su Windows, Linux e macOS. Il collaudo locale su Windows ha superato 27 test su entrambe le versioni. Le esecuzioni GitHub sulle altre piattaforme restano da verificare. I test usano dati sintetici e server di prova locali per IMAP e disiscrizioni.

Per eseguire le prove locali dopo l’installazione:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
