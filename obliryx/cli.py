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
                          mbox_messages, message_identities, scan_mail, scan_records, watch_eml)
from .multistep_demo import run_demo
from .network import post_form, resolve_destination
from .one_click import submit, verify_message
from .providers import breach_matches, search_web
from .site import discover_routes, fetch_html, inspect_page
from .store import Store, now
from .web_forms import discover_unsubscribe_form

REVIEWABLE_WEB_ROUTES = {"web_header", "web_body", "unsubscribe_candidate"}


def data_directory():
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "obliryx"


def parser():
    root = argparse.ArgumentParser(prog="obliryx", description="Registro locale di privacy personale")
    root.add_argument("--db", type=Path, default=data_directory() / "findings.sqlite3")
    commands = root.add_subparsers(dest="command", required=True)
    import_cmd = commands.add_parser("import-eml", help="Analizza un file .eml o una cartella di .eml")
    import_cmd.add_argument("path", type=Path)
    mbox_cmd = commands.add_parser("import-mbox", help="Analizza offline una casella esportata in MBOX")
    mbox_cmd.add_argument("path", type=Path)
    imap_cmd = commands.add_parser("import-imap", help="Analizza i messaggi recenti di una cartella IMAP in sola lettura")
    imap_cmd.add_argument("host", type=str.lower)
    imap_cmd.add_argument("--mailbox", default="INBOX")
    imap_cmd.add_argument("--limit", type=int, default=50)
    imap_cmd.add_argument("--auth", choices=("app-password", "xoauth2"), default="app-password")
    imap_cmd.add_argument("--match", choices=sorted(DATA_TYPES - {"credenziali"}), help="Cerca il tuo dato solo in locale")
    watch_cmd = commands.add_parser("watch-eml", help="Sorveglia una cartella locale di file .eml")
    watch_cmd.add_argument("path", type=Path)
    watch_cmd.add_argument("--interval", type=int, default=30, metavar="SECONDI")
    scan_cmd = commands.add_parser("scan-mail", help="Cerca un tuo dato nei contenuti della posta locale")
    scan_cmd.add_argument("path", type=Path)
    scan_cmd.add_argument("category", choices=sorted(DATA_TYPES - {"credenziali"}))
    commands.add_parser("campaigns", help="Raggruppa i riscontri email per mittente e lista dichiarati")
    breach_cmd = commands.add_parser("check-breach", help="Verifica una tua email presso Have I Been Pwned")
    breach_cmd.add_argument("--method", choices=("diretto", "prefisso"), required=True)
    commands.add_parser("search-web", help="Consulta risultati Brave in questa sessione")
    page_cmd = commands.add_parser("check-page", help="Verifica un tuo dato in una pagina HTML accessibile")
    page_cmd.add_argument("category", choices=sorted(DATA_TYPES - {"credenziali"}))
    recheck_cmd = commands.add_parser("recheck-page", help="Ricontrolla un dato già osservato alla stessa fonte")
    recheck_cmd.add_argument("id")
    commands.add_parser("record", help="Registra un’esposizione Web o un riscontro documentato")
    commands.add_parser("list", help="Elenca riscontri e gravità")
    show_cmd = commands.add_parser("show", help="Mostra prove, canali e storico di un riscontro")
    show_cmd.add_argument("id")
    review_cmd = commands.add_parser("review", help="Indica se riconosci l’iscrizione")
    review_cmd.add_argument("id")
    review_cmd.add_argument("state", choices=("da_verificare", "riconosciuta", "non_riconosciuta"))
    document_cmd = commands.add_parser("document", help="Aggiungi prove e contatto ufficiale a un riscontro")
    document_cmd.add_argument("id")
    controller_cmd = commands.add_parser("identify", help="Documenta l’identità del titolare associato a un riscontro")
    controller_cmd.add_argument("id")
    outcome_cmd = commands.add_parser("outcome", help="Registra l’esito osservato dall’utente")
    outcome_cmd.add_argument("id")
    outcome_cmd.add_argument("status", choices=("inviata", "rimozione_dichiarata", "dato_non_osservato", "ricomparsa", "non_verificabile"))
    draft_cmd = commands.add_parser("draft", help="Prepara una richiesta privacy o un messaggio di disiscrizione")
    draft_cmd.add_argument("id")
    kind = draft_cmd.add_mutually_exclusive_group()
    kind.add_argument("--route", type=int, help="Numero del percorso email, come in show")
    kind.add_argument("--action", choices=("opposizione", "cancellazione", "accesso"))
    draft_cmd.add_argument("--compose", action="store_true", help="Apri la bozza nel programma di posta")
    open_cmd = commands.add_parser("open-route", help="Apri un canale Web dopo la conferma")
    open_cmd.add_argument("id")
    open_cmd.add_argument("route", type=int)
    discover_cmd = commands.add_parser("find-routes", help="Cerca canali privacy su una pagina del titolare")
    discover_cmd.add_argument("id")
    confirm_cmd = commands.add_parser("confirm-route", help="Registra la verifica manuale di un canale di disiscrizione")
    confirm_cmd.add_argument("id")
    confirm_cmd.add_argument("route", type=int)
    form_cmd = commands.add_parser("form-unsubscribe", help="Compila un modulo semplice di disiscrizione")
    form_cmd.add_argument("id")
    form_cmd.add_argument("route", type=int)
    unsubscribe_cmd = commands.add_parser("unsubscribe", help="Esegui una disiscrizione one-click verificata")
    unsubscribe_cmd.add_argument("id")
    unsubscribe_cmd.add_argument("source", type=Path, help="File .eml originale o archivio .mbox che lo contiene")
    imap_unsubscribe = commands.add_parser("unsubscribe-imap", help="Recupera il messaggio IMAP e verifica il one-click")
    imap_unsubscribe.add_argument("id")
    imap_unsubscribe.add_argument("--source", type=int, help="Numero della fonte IMAP, da 1")
    imap_unsubscribe.add_argument("--auth", choices=("app-password", "xoauth2"), default="app-password")
    commands.add_parser("action-status", help="Mostra lo stato del registro e gli invii da verificare")
    commands.add_parser("action-reconcile", help="Riconcilia il registro invii dopo una verifica manuale")
    commands.add_parser("action-pause", help="Sospendi le nuove disiscrizioni POST dell’archivio")
    commands.add_parser("action-resume", help="Riabilita le nuove approvazioni per le disiscrizioni POST")
    commands.add_parser("backup", help="Copia l’archivio cifrato in un nuovo file").add_argument("destination", type=Path)
    commands.add_parser("restore", help="Copia il backup indicato in --db in un nuovo archivio").add_argument(
        "destination", type=Path)
    commands.add_parser("export", help="Esporta un riepilogo locale in JSON in chiaro").add_argument(
        "destination", type=Path)
    commands.add_parser("rotate-passphrase", help="Sostituisci la passphrase dell’archivio")
    catalog = commands.add_parser("broker-catalog", help="Consulta il catalogo locale di procedure broker")
    catalog.add_argument("procedure", nargs="?", metavar="ID")
    demo = commands.add_parser("multistep-demo", help="Prova l’adattatore su un sito HTTPS locale controllato")
    demo.add_argument("--port", type=int, required=True)
    demo.add_argument("--ca", type=Path, required=True, help="Certificato PEM della CA del sito di prova")
    return root


from .services import (approve, emit, evidence_details, import_eml, run, unsubscribe,
                       execute_one_click, form_unsubscribe, lookup_web, page_identity)


def main():
    args = parser().parse_args()
    try:
        if args.command == "broker-catalog":
            emit(catalog_view(args.procedure))
            return 0
        if not sys.stdin.isatty():
            raise ValueError("Usa un terminale interattivo per sbloccare l’archivio.")
        if args.command == "multistep-demo":
            emit(run_demo(args.port, args.ca, approve))
            return 0
        if args.command == "search-web":
            lookup_web()
            return 0
        if args.command in {"backup", "restore", "export", "rotate-passphrase",
                            "action-status", "action-pause", "action-resume", "action-reconcile"} and not args.db.is_file():
            raise ValueError("L’archivio indicato non esiste.")
        password = getpass.getpass("Passphrase archivio: ")
        with closing(Store(args.db, password, ledger_dir=data_directory() / "action-state",
                           readonly=args.command == "restore")) as store:
            return run(store, args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
    except (OSError, sqlite3.Error):
        print("Errore di accesso al file, all’archivio o alla rete.", file=sys.stderr)
    except (EOFError, KeyboardInterrupt):
        print("Operazione interrotta.", file=sys.stderr)
    return 1
