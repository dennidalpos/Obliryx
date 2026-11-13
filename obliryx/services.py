import argparse
import getpass
import json
import os
import re
import sqlite3
import sys
import webbrowser
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from .analysis import DATA_TYPES, address, https_url, normalized, severity
from .broker_catalog import catalog_view
from .imap_source import recent_messages, retrieve_message, validate_destination
from .mail_import import (campaign_summary, collect, collect_records, eml_messages, find_original,
                          mail_source, mbox_messages, message_identities, scan_mail, scan_records, watch_eml)
from .multistep_demo import run_demo
from .network import post_form, resolve_destination
from .one_click import submit, verify_message
from .providers import breach_matches, search_web
from .site import discover_routes, fetch_html, inspect_page
from .store import Store, now
from .web_forms import discover_unsubscribe_form

from .interaction import ask, checked, current


REVIEWABLE_WEB_ROUTES = {"web_header", "web_body", "unsubscribe_candidate"}


def import_eml(store, path):
    counts = collect(store, checked(eml_messages(path)))
    emit(counts)
    return 1 if counts["errori"] else 0


def evidence_details(previous=None):
    previous = previous or {}
    def detail(label):
        return ask(label + (" [Invio mantiene il valore]" if previous else "") + ": ").strip()

    current.get().notify("Categorie ammesse: " + ", ".join(sorted(DATA_TYPES)))
    category_text = detail("Categorie effettivamente osservate, separate da virgola")
    types = (set(category_text.lower().replace(" ", "").split(",")) - {""}
             if category_text else set(previous.get("data_types", [])))
    if types - DATA_TYPES:
        raise ValueError("Categorie non valide.")
    answer = detail("Hai una prova dell’acquisto dei dati? [s/n]").lower()
    acquisition = {"s": "acquisto_documentato", "n": "ignota"}.get(answer)
    if answer and not acquisition:
        raise ValueError("Rispondi s oppure n.")
    acquisition = acquisition or previous.get("acquisition", "ignota")
    new_evidence = detail("Riferimento o nota di prova, senza riportare i dati sensibili")
    evidence = new_evidence or previous.get("evidence", "")
    privacy_email = detail("Contatto email verificato sul sito ufficiale (facoltativo)") or previous.get("privacy_email")
    already_documented = previous.get("acquisition") == "acquisto_documentato" and previous.get("evidence")
    if acquisition == "acquisto_documentato" and not (new_evidence or already_documented):
        raise ValueError("L’acquisto documentato richiede un riferimento alla prova.")
    if privacy_email and not address(privacy_email):
        raise ValueError("Contatto email non valido.")
    return {"data_types": sorted(types), "acquisition": acquisition,
            "evidence": evidence[:2000], "privacy_email": privacy_email or None}


def record(store):
    controller = ask("Organizzazione o sito osservato: ").strip()
    source = ask("URL HTTPS della fonte (facoltativo): ").strip()
    route = ask("URL HTTPS della disiscrizione ufficiale (facoltativo): ").strip()
    if not controller or (source and not https_url(source)) or (route and not https_url(route)):
        raise ValueError("Organizzazione o URL non validi.")
    finding = {
        "source": "riscontro_manual", "recorded_at": now(), "controller": controller[:250],
        "source_url": source or None, "sender": None, "list_id": "", "subject": "",
        "indicators": [], "enrollment": "da_verificare", **evidence_details(),
        "routes": [{"kind": "web_manual", "value": route}] if route else [],
    }
    identity = json.dumps({key: value for key, value in finding.items() if key != "recorded_at"},
                          sort_keys=True).encode()
    finding_id, created = store.save(finding, b"manual\x00" + identity)
    emit({"id": finding_id, "nuovo": created})


def emit(value):
    current.get().emit(value)


def get_route(finding, index):
    routes = finding["routes"]
    if index < 1 or index > len(routes):
        raise ValueError("Numero del canale inesistente.")
    return routes[index - 1]


def draft(finding, route_index, action):
    if route_index is not None:
        route = get_route(finding, route_index)
        if route["kind"] != "email_header":
            raise ValueError("Il canale selezionato non è un indirizzo email di disiscrizione.")
        target = urlsplit(route["value"])
        fields = dict(parse_qsl(target.query, max_num_fields=12))
        return {"destinatario": target.path, "oggetto": fields.get("subject", "Richiesta di disiscrizione"),
                "testo": fields.get("body", "Chiedo di rimuovere il mio indirizzo da questa lista.")}
    if finding["source"] == "hibp":
        raise ValueError("Per una violazione registrata da HIBP, verifica prima il canale del servizio coinvolto.")
    if action is None:
        action = "opposizione" if finding["source"] == "messaggio_importato" else "cancellazione"
    title, body = {
        "opposizione": ("Opposizione al marketing diretto",
                        "Chiedo di interrompere il trattamento del mio indirizzo per finalità di marketing diretto "
                        "e di rimuoverlo dalle relative liste."),
        "cancellazione": ("Richiesta di cancellazione dei dati personali",
                          "Chiedo di cancellare i dati personali che mi riguardano indicati in [URL o riferimento]. "
                          "Il motivo della richiesta è [motivo pertinente]."),
        "accesso": ("Richiesta di accesso ai dati personali",
                    "Chiedo conferma del trattamento dei dati personali che mi riguardano, accesso a tali dati "
                    "e le informazioni disponibili sulla loro origine quando sono stati raccolti presso terzi."),
    }[action]
    return {"destinatario": finding.get("privacy_email"), "oggetto": title,
            "testo": body + " Contatto per il riscontro: [indirizzo]. Vi chiedo conferma del riscontro."}


def compose(message):
    recipient = message["destinatario"]
    if not recipient or not address(recipient):
        raise ValueError("Aggiungi un contatto email ufficiale con il comando document.")
    approve(message, "Controlla il destinatario e il testo prima di aprire il client di posta.")
    subject = re.sub(r"[\x00-\x1f\x7f]", " ", message["oggetto"])
    fields = urlencode({"subject": subject, "body": message["testo"]}, quote_via=quote)
    if not webbrowser.open("mailto:" + quote(recipient, safe="@") + "?" + fields):
        raise ValueError("Impossibile aprire il client di posta predefinito.")


def approve(value, prompt):
    current.get().approve(value, prompt)
    current.get().check()


def check_breach(store, method):
    email = ask("Tua email da verificare: ", secret=True).strip().lower()
    if not address(email):
        raise ValueError("Indirizzo email non valido.")
    key = ask("Chiave API HIBP: ", secret=True).strip()
    shared = "email completa" if method == "diretto" else "prefisso SHA-1 di 6 caratteri (piano Pro o High RPM)"
    approve({"fornitore": "Have I Been Pwned", "dati_trasmessi": shared},
            "Conferma che stai verificando un tuo indirizzo e autorizzi la ricerca.")
    records = breach_matches(email, key, method)
    for item in records:
        name = item["Name"]
        classes = item.get("DataClasses")
        finding = {
            "source": "hibp", "provider_url": "https://haveibeenpwned.com/", "recorded_at": now(),
            "controller": name, "subject": "", "sender": None, "identifier": email,
            "data_types": ["email"], "incident_data_types": classes if isinstance(classes, list) else [],
            "verified_incident": item.get("IsVerified"), "spam_list": item.get("IsSpamList"),
            "acquisition": "ignota", "enrollment": "da_verificare", "routes": [],
        }
        store.save(finding, b"hibp\x00" + json.dumps([email, name]).encode())
    emit({"fonte": "Have I Been Pwned", "attribuzione": "https://haveibeenpwned.com/",
          "riscontri": len(records), "copertura": "Incidenti restituiti da HIBP per questo controllo"})


def lookup_web():
    query = ask("Tua email, username o nome da cercare: ", secret=True).strip()
    if not address(query) and (not 3 <= len(query) <= 100 or not re.fullmatch(r"[\w .’'@-]+", query)):
        raise ValueError("Identificativo non valido per la ricerca esatta.")
    key = ask("Chiave Brave Search API: ", secret=True).strip()
    approve({"fornitore": "Brave Search API", "dati_trasmessi": "identificativo completo"},
            "Conferma che l’identificativo è tuo e autorizzi la ricerca.")
    emit({"fonte": "Brave Search API", "risultati_transitori": search_web(query, key),
          "verifica": "Apri la pagina originale e verifica il dato alla fonte prima di registrare un riscontro."})


def page_identity(url, category, value):
    return b"page\x00" + json.dumps([url, category, value]).encode()


def check_page(store, category):
    url = ask("URL HTTPS della pagina originale: ", secret=True).strip()
    value = ask("Tuo dato da cercare nella pagina: ", secret=True).strip()
    if not https_url(url) or not 5 <= len(value) <= 200:
        raise ValueError("URL o valore da cercare non valido.")
    approve({"azione": "GET", "destinazione": url, "dato_trasmesso": "solo URL e metadati di connessione"},
            "Conferma che il dato da verificare è tuo e che la pagina è quella da consultare.")
    matched, routes = inspect_page(url, value)
    routes = [{**route, "source_url": url} for route in routes]
    report = {"dato_osservato": matched, "canali_candidati": routes}
    if matched:
        timestamp = now()
        finding = {"source": "pagina_verificata", "recorded_at": timestamp, "source_url": url,
                   "controller": urlsplit(url).hostname, "subject": "", "sender": None,
                   "data_types": [category], "routes": routes, "acquisition": "ignota",
                   "enrollment": "da_verificare", "evidence": "Corrispondenza testuale con un valore fornito dall’utente.",
                   "page_category": category, "web_checks": [{"status": "dato_osservato", "checked_at": timestamp}]}
        canonical = normalized(value)
        legacy = (page_identity(url, category, value),) if canonical != value else ()
        report["id"], report["nuovo"] = store.save(finding, page_identity(url, category, canonical),
                                                  alternate_identities=legacy)
        if not report["nuovo"]:
            report["ultimo_controllo_web"] = store.record_web_check(report["id"], True)
    emit(report)


def recheck_page(store, finding_id, finding):
    url = finding.get("source_url")
    if finding["source"] != "pagina_verificata" or not https_url(url):
        raise ValueError("Scegli un riscontro creato con check-page.")
    value = ask("Inserisci lo stesso dato osservato in origine: ", secret=True).strip()
    if not 5 <= len(value) <= 200:
        raise ValueError("Valore di confronto non valido.")
    categories = (finding["page_category"],) if "page_category" in finding else sorted(DATA_TYPES - {"credenziali"})
    variants = {value, normalized(value)}
    if not any(store.matches(finding_id, page_identity(url, category, variant))
               for category in categories for variant in variants):
        raise ValueError("Il dato inserito non coincide con quello del riscontro originale.")
    approve({"azione": "GET", "destinazione": url, "riscontro": finding_id},
            "Conferma il ricontrollo alla stessa fonte. Il valore viene confrontato in locale.")
    try:
        observed, _ = inspect_page(url, value)
    except (ValueError, OSError) as exc:
        reason = str(exc) if isinstance(exc, ValueError) else "Connessione alla fonte non disponibile."
        emit(store.record_web_check(finding_id, None, reason))
        return 1
    emit(store.record_web_check(finding_id, observed))
    return 0


def find_routes(store, finding_id, finding):
    url = ask("Pagina HTTPS informativa del soggetto, senza parametri: ").strip()
    if not https_url(url) or urlsplit(url).query:
        raise ValueError("Indica una pagina informativa HTTPS pubblica senza parametri personali.")
    approve({"azione": "GET", "destinazione": url,
             "soggetto_dichiarato": finding.get("controller") or finding["sender"]},
            "Conferma la pagina pubblica. I collegamenti trovati verranno registrati come candidati.")
    candidates = discover_routes(url)
    emit({"canali_candidati": candidates, "aggiunti": store.add_routes(finding_id, candidates)})


def identify_controller(store, finding_id, finding):
    name = ask("Denominazione pubblica del titolare: ").strip()
    url = ask("URL HTTPS informativo che indica il titolare, senza parametri: ").strip()
    reason = ask("Collegamento tra questa fonte e il riscontro, senza inserire dati personali: ").strip()
    if not 3 <= len(name) <= 250 or not 10 <= len(reason) <= 1000 or not https_url(url) or urlsplit(url).query:
        raise ValueError("Indica una denominazione, una fonte informativa HTTPS e il collegamento al riscontro.")
    approve({"azione": "GET", "destinazione": url}, "Conferma il controllo della fonte pubblica.")
    observed, _ = inspect_page(url, name)
    if not observed:
        raise ValueError("La denominazione non compare nel testo accessibile della fonte.")
    approve({"soggetto_dichiarato": finding.get("controller") or finding["sender"],
             "titolare_proposto": name, "fonte": url, "collegamento": reason},
            "Conferma solo se hai verificato che la fonte riguarda il titolare di questo riscontro.")
    emit(store.record_controller(finding_id, name, url, reason))


def imap_credential(method):
    prompt = "Token di accesso OAuth IMAP: " if method == "xoauth2" else "Password per app del provider IMAP: "
    return ask(prompt, secret=True)


def mail_scan_value(category):
    value = ask("Tuo dato da cercare nella posta (solo confronto locale): ", secret=True).strip()
    if not 5 <= len(value) <= 200 or (category == "email" and not address(value)):
        raise ValueError("Il valore deve essere valido per la categoria e lungo tra 5 e 200 caratteri.")
    return value


def import_imap(store, args):
    if not 1 <= args.limit <= 500:
        raise ValueError("Scegli un limite da 1 a 500 messaggi.")
    validate_destination(args.host, args.mailbox)
    user = ask("Nome utente della tua casella IMAP: ", secret=True).strip()
    value = mail_scan_value(args.match) if args.match else None
    approve({"azione": "lettura IMAP", "server": args.host, "porta": 993, "cartella": args.mailbox,
             "utente": user, "limite": args.limit}, "Conferma il server ufficiale della tua casella.")
    credential = imap_credential(args.auth)
    with closing(recent_messages(args.host, user, args.mailbox, args.auth, credential, args.limit)) as records:
        counts = scan_records(store, checked(records), args.match, value) if args.match else collect_records(store, checked(records))
    emit(counts)
    return 1 if counts["errori"] else 0


def one_click_destination(finding):
    candidates = [route for route in finding["routes"] if route["kind"] == "one_click_candidate"]
    if len(candidates) != 1 or not https_url(candidates[0]["value"]):
        raise ValueError("Il messaggio non propone un canale HTTPS one-click univoco.")
    return candidates[0]["value"]


def execute_one_click(store, finding_id, finding, raw, url):
    checkpoint = store.review_action(finding_id, finding)
    recipient = ask("Indirizzo destinatario di cui hai il controllo: ").strip()
    verify_message(raw, finding["sender"], recipient, destination=url)
    preview = {"azione": "POST List-Unsubscribe=One-Click", "mittente_dkim": finding["sender"],
               "destinatario_verificato": recipient, "destinazione": url}
    approve(preview, "Verifica il mittente e la destinazione prima dell’invio.")
    ip = resolve_destination(urlsplit(url).hostname)
    current.get().begin_effect()
    action_id = store.start_action(finding_id, url, preview={**preview, "sha256_messaggio": sha256(raw).hexdigest()},
                                   reviewed_checkpoint=checkpoint, reviewed_finding=finding)
    status = submit(url, ip)
    store.finish_action(action_id, status)
    emit({"id_azione": action_id, "stato": status, "rimozione_verificata": False})
    return 0 if status == "accepted" else 1


def unsubscribe(store, finding_id, finding, file):
    url = one_click_destination(finding)
    return execute_one_click(store, finding_id, finding, find_original(store, finding_id, file), url)


def unsubscribe_imap(store, finding_id, finding, source_index, method):
    url = one_click_destination(finding)
    store.review_action(finding_id, finding)
    sources = finding.get("imap_sources", [])
    if source_index is None and len(sources) == 1:
        source_index = 1
    if source_index is None or not 1 <= source_index <= len(sources):
        raise ValueError("Scegli una fonte IMAP del riscontro con --source N oppure usa il file originale.")
    source = sources[source_index - 1]
    approve({"azione": "recupero messaggio IMAP", "server": source["host"], "porta": 993,
             "cartella": source["mailbox"], "utente": source["user"]},
            "Conferma il recupero del messaggio. La disiscrizione sarà approvata separatamente.")
    raw = retrieve_message(source, method, imap_credential(method))
    if not any(store.matches(finding_id, identity) for identity in message_identities(raw)):
        raise ValueError("Il messaggio IMAP recuperato non coincide con quello registrato.")
    return execute_one_click(store, finding_id, finding, raw, url)


def form_unsubscribe(store, finding_id, finding, index):
    route = get_route(finding, index)
    url = https_url(route["value"])
    is_form_route = route["kind"] == "web_manual" or (
        route["kind"] in REVIEWABLE_WEB_ROUTES and route.get("confirmed_at")
    )
    if not url or not is_form_route:
        raise ValueError("Seleziona un canale Web di disiscrizione pertinente e conferma i candidati con confirm-route.")
    checkpoint = store.review_action(finding_id, finding)
    approve({"azione": "GET", "destinazione": url,
             "soggetto_dichiarato": finding.get("controller") or finding["sender"],
             "provenienza": route.get("source_url", route["kind"])},
            "Conferma la lettura iniziale e il ricontrollo del modulo prima del POST. Aprire il link può avere effetti.")
    ip = resolve_destination(urlsplit(url).hostname)
    form = discover_unsubscribe_form(url, fetch_html(url, ip))
    email = ask("Tuo indirizzo da disiscrivere: ", secret=True).strip()
    if not address(email):
        raise ValueError("Indirizzo email non valido.")
    fields = form.payload(email)
    body = urlencode(fields).encode("ascii")
    preview = {"azione": "POST", "destinazione": form.destination, "pulsante": form.label, "campi": fields}
    approve(preview, "Controlla destinatario e campi. Conferma l’invio solo per il tuo indirizzo.")
    if store.review_action(finding_id, finding) != checkpoint:
        raise ValueError("Il registro è cambiato. Genera una nuova anteprima.")
    try:
        current_form = discover_unsubscribe_form(url, fetch_html(url, ip))
    except ValueError:
        raise ValueError("Impossibile ricontrollare il modulo. Genera una nuova anteprima.") from None
    if current_form != form:
        raise ValueError("La procedura è cambiata. Genera una nuova anteprima.")
    current.get().begin_effect()
    action_id = store.start_action(finding_id, form.destination, form_address=email, form_page=url,
                                   preview={**preview, "pagina": url, "corpo": body.decode("ascii")},
                                   reviewed_checkpoint=checkpoint, reviewed_finding=finding)
    status = post_form(form.destination, ip, body)
    store.finish_action(action_id, status)
    emit({"id_azione": action_id, "stato": status, "rimozione_verificata": False})
    return 0 if status == "accepted" else 1


def run(store, args):
    current.get().check()
    match args.command:
        case "action-status":
            emit({**store.action_status(), "file_registro": str(store.ledger_path)})
        case "action-reconcile":
            reviewed = store.action_status()
            approve(reviewed, "Verifica presso la fonte gli invii possibili dopo la copia, anche se il registro manca. "
                    "Conferma solo dopo il controllo. Le destinazioni già registrate restano bloccate.")
            store.reconcile_actions(reviewed)
            emit(store.action_status())
        case "action-pause":
            store.set_actions_paused(True)
            emit(store.action_status())
        case "action-resume":
            approve({"azione": "riabilita le nuove approvazioni POST"},
                    "Conferma la riattivazione. Ogni invio richiederà una nuova anteprima.")
            store.set_actions_paused(False)
            emit(store.action_status())
        case "backup" | "restore" | "export":
            description = {
                "backup": "crea una copia cifrata dell’archivio",
                "restore": "ripristina in un nuovo file, mantenendo il registro invii sul dispositivo",
                "export": "scrivi un riepilogo JSON in chiaro. Il file può contenere dati personali",
            }
            approve({"operazione": description[args.command], "destinazione": str(args.destination.resolve())},
                    "Verifica il percorso e chi può accedervi prima di confermare.")
            if args.command == "export":
                store.export_to(args.destination)
            else:
                store.backup_to(args.destination)
            emit({"operazione": args.command, "stato": "completata"})
        case "rotate-passphrase":
            password = ask("Nuova passphrase (almeno 12 caratteri): ", secret=True)
            if password != ask("Ripeti la nuova passphrase: ", secret=True):
                raise ValueError("Le nuove passphrase non coincidono.")
            approve({"operazione": "sostituisci la passphrase di questo archivio"},
                    "Le copie esistenti continuano a richiedere la loro passphrase originale.")
            store.rotate_password(password)
            emit({"operazione": args.command, "stato": "completata"})
        case "import-eml":
            return import_eml(store, args.path)
        case "import-mbox":
            counts = collect(store, checked(mbox_messages(args.path)))
            emit(counts)
            return 1 if counts["errori"] else 0
        case "import-imap":
            return import_imap(store, args)
        case "watch-eml":
            if not 1 <= args.interval <= 3600:
                raise ValueError("L’intervallo deve essere tra 1 e 3600 secondi.")
            print("Monitoraggio locale attivo. Premi Ctrl+C per terminarlo.", file=sys.stderr)
            try:
                for counts in watch_eml(store, args.path, args.interval):
                    emit(counts)
            except KeyboardInterrupt:
                return 0
        case "scan-mail":
            value = mail_scan_value(args.category)
            with closing(mail_source(args.path)) as messages:
                counts = scan_records(store, checked((raw, None) for raw in messages), args.category, value)
            emit(counts)
            return 1 if counts["errori"] else 0
        case "campaigns":
            emit(campaign_summary(store.all()))
        case "check-breach":
            check_breach(store, args.method)
        case "check-page":
            check_page(store, args.category)
        case "record":
            record(store)
        case "list":
            summaries = [{"id": finding_id, "fonte": item.get("provider_url", item["source"]),
                          "soggetto_dichiarato": item.get("controller") or item["sender"],
                          "titolare_revisionato": (item.get("controller_reviews") or [{}])[-1].get("name"),
                          "gravita": severity(item)[0], "iscrizione": item["enrollment"],
                          "ultimo_controllo_web": (item.get("web_checks") or [None])[-1],
                          "canali": len(item["routes"])} for finding_id, item in store.all()]
            order = {"alta": 0, "media": 1, "bassa": 2}
            emit(sorted(summaries, key=lambda item: order[item["gravita"]]))
        case "review":
            store.update(args.id, enrollment=args.state)
        case "outcome":
            store.record_outcome(args.id, args.status)
        case _:
            finding = store.get(args.id)
            if args.command == "show":
                level, reason = severity(finding)
                finding["routes"] = [{"numero": i, **route} for i, route in enumerate(finding["routes"], 1)]
                emit({"id": args.id, "gravita": level, "motivo": reason, **finding,
                      "azioni": store.actions(args.id)})
            elif args.command == "draft":
                message = draft(finding, args.route, args.action)
                if args.compose:
                    compose(message)
                else:
                    emit(message)
            elif args.command == "document":
                if finding["source"] == "hibp":
                    raise ValueError("Registra eventuali prove indipendenti con il comando record.")
                store.update(args.id, **evidence_details(finding))
            elif args.command == "identify":
                identify_controller(store, args.id, finding)
            elif args.command == "open-route":
                route = get_route(finding, args.route)
                if not https_url(route["value"]):
                    raise ValueError("Il canale selezionato non è un URL HTTPS.")
                approve(route, "Controlla la provenienza del link. Aprirlo contatta il sito e può disiscriverti.")
                if not webbrowser.open(route["value"], new=2):
                    raise ValueError("Impossibile aprire il browser predefinito.")
            elif args.command == "find-routes":
                find_routes(store, args.id, finding)
            elif args.command == "recheck-page":
                return recheck_page(store, args.id, finding)
            elif args.command == "confirm-route":
                route = get_route(finding, args.route)
                if route["kind"] not in REVIEWABLE_WEB_ROUTES:
                    raise ValueError("Seleziona un candidato Web alla disiscrizione.")
                approve(route, "Conferma solo se hai verificato la pertinenza della procedura per questo riscontro.")
                store.confirm_route(args.id, route["kind"], route["value"])
            elif args.command == "unsubscribe":
                return unsubscribe(store, args.id, finding, args.source)
            elif args.command == "unsubscribe-imap":
                return unsubscribe_imap(store, args.id, finding, args.source, args.auth)
            elif args.command == "form-unsubscribe":
                return form_unsubscribe(store, args.id, finding, args.route)
    return 0
