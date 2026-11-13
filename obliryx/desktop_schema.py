"""The desktop bridge accepts only these named, structured operations."""

def field(key, label, kind="text", choices=None, default="", required=True):
    return dict(key=key, label=label, kind=kind, choices=choices, default=default, required=required)


PATH = field("path", "File o cartella", "path")
ROUTE = field("route", "Numero del canale", "number", default="1")
CATEGORY = field("category", "Categoria del tuo dato", "select",
                 ["email", "nome", "username", "telefono", "indirizzo", "documento", "finanziari", "salute"])
AUTH = field("auth", "Metodo di accesso", "select", ["app-password", "xoauth2"])
DEST = field("destination", "Nuovo file di destinazione", "save")

# Positional argument order is explicit; optional flags cannot become commands.
OPERATIONS = {
    "import-eml": ("Importa EML o cartella", "import", [PATH]),
    "import-mbox": ("Importa MBOX", "import", [PATH]),
    "watch-eml": ("Monitora una cartella EML", "import", [PATH, field("interval", "Intervallo in secondi", "number", default="30")]),
    "import-imap": ("Leggi la tua casella IMAP", "import", [field("host", "Server IMAP ufficiale"), field("mailbox", "Cartella", default="INBOX"), field("limit", "Messaggi recenti (1–500)", "number", default="50"), AUTH, field("match", "Confronto locale facoltativo", "select", ["", *CATEGORY["choices"]], required=False)]),
    "scan-mail": ("Cerca un tuo dato nella posta", "search", [PATH, CATEGORY]),
    "check-page": ("Verifica una pagina Web", "search", [CATEGORY]),
    "check-breach": ("Verifica con Have I Been Pwned", "search", [field("method", "Dati trasmessi al provider", "select", ["diretto", "prefisso"])]),
    "search-web": ("Cerca con Brave", "search", []),
    "record": ("Registra un riscontro verificato", "search", []),
    "campaigns": ("Raggruppa le campagne", "findings", []),
    "review": ("Rivedi l’iscrizione", "detail", [field("state", "Riconosci l’iscrizione?", "select", ["da_verificare", "riconosciuta", "non_riconosciuta"])]),
    "document": ("Documenta le prove e il contatto", "detail", []),
    "identify": ("Verifica il titolare", "detail", []),
    "outcome": ("Registra un esito osservato", "detail", [field("status", "Esito dichiarato da te", "select", ["inviata", "rimozione_dichiarata", "dato_non_osservato", "ricomparsa", "non_verificabile"])]),
    "draft": ("Prepara una richiesta", "detail", [field("action", "Tipo di richiesta", "select", ["opposizione", "cancellazione", "accesso"])]),
    "draft-route": ("Bozza dal canale email", "detail", [ROUTE]),
    "compose-route": ("Apri la bozza del canale email nel client", "detail", [ROUTE]),
    "compose": ("Apri la richiesta nel client email", "detail", [field("action", "Tipo di richiesta", "select", ["opposizione", "cancellazione", "accesso"])]),
    "find-routes": ("Cerca canali alla fonte", "detail", []),
    "confirm-route": ("Verifica il canale candidato", "detail", [ROUTE]),
    "open-route": ("Apri il canale nel browser", "detail", [ROUTE]),
    "form-unsubscribe": ("Disiscrivi con modulo semplice", "detail", [ROUTE]),
    "unsubscribe": ("Disiscrivi con one-click verificato", "detail", [field("source", "Messaggio originale EML o MBOX", "path")]),
    "unsubscribe-imap": ("Recupera l’originale IMAP e disiscrivi", "detail", [field("source", "Numero fonte IMAP", "number", required=False), AUTH]),
    "recheck-page": ("Ricontrolla la fonte", "detail", []),
    "action-status": ("Controlla il registro invii", "archive", []),
    "action-pause": ("Sospendi gli invii", "archive", []),
    "action-resume": ("Riabilita gli invii", "archive", []),
    "action-reconcile": ("Riconcilia il registro invii", "archive", []),
    "backup": ("Crea una copia cifrata", "archive", [DEST]),
    "restore": ("Ripristina in un nuovo file", "archive", [DEST]),
    "export": ("Esporta riepilogo JSON in chiaro", "archive", [DEST]),
    "rotate-passphrase": ("Cambia la passphrase", "archive", []),
}

POSITIONAL = {
    "import-eml": ["path"], "import-mbox": ["path"], "watch-eml": ["path"],
    "import-imap": ["host"], "scan-mail": ["path", "category"], "check-page": ["category"],
    "review": ["id", "state"], "outcome": ["id", "status"],
    "unsubscribe": ["id", "source"], "backup": ["destination"],
    "restore": ["destination"], "export": ["destination"],
    **{key: ["id", "route"] for key in ["open-route", "confirm-route", "form-unsubscribe"]},
    **{key: ["id"] for key in ["draft", "document", "identify", "find-routes", "recheck-page", "unsubscribe-imap"]},
}
