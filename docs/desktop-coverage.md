# Copertura CLI → desktop

| Capacità CLI | Percorso grafico | Implementazione |
|---|---|---|
| import-eml, import-mbox, import-imap, watch-eml | Importa e monitora | Servizi condivisi; monitoraggio di sessione nel worker |
| scan-mail, search-web, check-page, check-breach, record | Ricerche | Campi transitori e conferme separate |
| list, show | Riscontri | Elenco paginato, filtri e dettaglio |
| campaigns | Riscontri → Raggruppa campagne | Risultato strutturato |
| review, document, identify, outcome | Dettaglio → Altre azioni | Stessi servizi e validazioni della CLI |
| draft, --route, --compose | Dettaglio → Altre azioni | Bozza, canale email e client esterno |
| find-routes, confirm-route, open-route | Dettaglio → Altre azioni | Candidati, verifica e apertura approvata |
| unsubscribe, unsubscribe-imap, form-unsubscribe | Dettaglio → Altre azioni | DKIM, anteprima, CONFERMO, registro e deduplicazione |
| recheck-page | Dettaglio → Ricontrolla la fonte | Verifica del valore originale e storico |
| backup, restore, export, rotate-passphrase | Archivio | Nuovi file, avvisi e conferme |
| action-status/pause/resume/reconcile | Archivio | Registro condiviso con la CLI |
| broker-catalog | Procedure broker | Catalogo e dettaglio con revisione |
| multistep-demo | CLI tecnica | Esclusa dalla GUI utente; collaudo sintetico separato |

Rinviati: nuove automazioni, scheduler, IMAP incrementale, nuove pratiche e scadenze. Le funzionalità della specifica storica che eccedono la CLI non sono promesse dalla UI. La qualificazione di provider reali resta separata dai test locali.
