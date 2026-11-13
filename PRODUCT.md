# Obliryx

<!-- impeccable:product-schema 1 -->

## Users and purpose

Cittadini che inseriscono i propri identificativi per cercare tracce pubbliche dei dati e scegliere gli interventi, senza terminale. L’ingresso principale è la ricerca Web, senza importazione della posta o gestione manuale dell’archivio. Una corrispondenza testuale non prova l’identità; una scheda broker non prova il possesso dei dati.

## Platform and stack

Windows 11 x64; React e TypeScript in pywebview/WebView2, motore Python e SQLite cifrato. Cinque fasi: dati, analisi, selezione, approvazione, interventi. Browser WebView2 InPrivate separato dal bridge privilegiato, senza oggetti host o messaggi Web. Le funzioni precedenti restano nella CLI e nell’apertura facoltativa degli archivi precedenti.

## Constraints

Nessun account Obliryx, telemetria o API a pagamento. Credenziale locale automatica protetta da Windows DPAPI; identificativi transitori. Fonti gratuite: GitHub pubblico e Wikipedia italiana, con trasmissioni dichiarate prima dell’analisi e copertura limitata. DuckDuckGo solo tramite link esterno per il divieto di incorporamento. Approvazione unica del lotto, adattatori con contratti esatti e registro contro duplicati; CAPTCHA e verifiche in fondo alla coda. I vincoli degli invii HTTP della CLI restano distinti e invariati. Una risposta accepted non prova la rimozione.

## Success

Aprire l’app senza password aggiuntiva, inserire almeno un identificativo, analizzare le fonti consultabili, selezionare e approvare il lotto, poi completare le verifiche assistite. Nessuna promessa di ricerca universale. Gli automatismi sono collaudati con dati sintetici; il catalogo reale rimane manuale finché ogni adattatore non viene qualificato. Nessuno scheduler.
