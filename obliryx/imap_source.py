import imaplib
import re
import ssl
from contextlib import contextmanager

from .analysis import HOST, MAX_MESSAGE_BYTES

UID = re.compile(rb"\bUID (\d+)\b", re.I)
SIZE = re.compile(rb"\bRFC822\.SIZE (\d+)\b", re.I)


class BoundedIMAP(imaplib.IMAP4_SSL):
    def read(self, size):
        if size > MAX_MESSAGE_BYTES + 1:
            raise imaplib.IMAP4.abort("Risposta IMAP troppo grande")
        return super().read(size)


def imap_string(value):
    if not 1 <= len(value) <= 320 or not value.isascii() or not value.isprintable():
        raise ValueError("Nome IMAP non valido. Usa caratteri ASCII stampabili.")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def validate_destination(host, mailbox):
    if not HOST.fullmatch(host):
        raise ValueError("Indica il nome DNS del server IMAP, senza porta o percorso.")
    imap_string(mailbox)


@contextmanager
def open_mailbox(host, user, mailbox, method, credential):
    validate_destination(host, mailbox)
    quoted_user = imap_string(user)
    if not 1 <= len(credential) <= 8192 or not credential.isascii() or not credential.isprintable():
        raise ValueError("Credenziale IMAP non valida.")
    try:
        with BoundedIMAP(host, ssl_context=ssl.create_default_context(), timeout=12) as client:
            if method == "xoauth2":
                if "AUTH=XOAUTH2" not in client.capabilities:
                    raise ValueError("Il server non dichiara il supporto XOAUTH2.")
                responses = iter((f"user={user}\x01auth=Bearer {credential}\x01\x01".encode("ascii"),))
                status, _ = client.authenticate("XOAUTH2", lambda _challenge: next(responses, b""))
            else:
                status, _ = client.login(quoted_user, credential)
            if status != "OK":
                raise ValueError("Autenticazione IMAP rifiutata.")
            status, count = client.select(imap_string(mailbox), readonly=True)
            if status != "OK" or not count or count[0] is None or not count[0].isdigit():
                raise ValueError("Cartella IMAP non leggibile in sola lettura.")
            _, validity = client.response("UIDVALIDITY")
            if not validity or validity[0] is None or not validity[0].isdigit():
                raise ValueError("Il server non ha fornito UIDVALIDITY per la cartella.")
            yield client, int(count[0]), int(validity[0])
    except ssl.SSLCertVerificationError:
        raise ValueError("Certificato del server IMAP non attendibile.") from None
    except (OSError, imaplib.IMAP4.error):
        raise ValueError("Connessione o risposta IMAP non valida. Controlla il server, la credenziale e la cartella.") from None


def fetch_message(client, uid):
    if type(uid) is not int or not 0 < uid <= 2**32 - 1:
        raise ValueError("UID IMAP non valido.")
    status, chunks = client.uid("FETCH", str(uid), f"(UID RFC822.SIZE BODY.PEEK[]<0.{MAX_MESSAGE_BYTES + 1}>)")
    if status != "OK" or not chunks:
        return None
    literals = [(index, item) for index, item in enumerate(chunks) if isinstance(item, tuple)]
    if len(literals) != 1:
        return None
    index, (header, raw) = literals[0]
    if not re.search(rb"\bBODY\[\](?:<0>)?\s+\{\d+\}$", header, re.I):
        return None
    tail = chunks[index + 1] if index + 1 < len(chunks) else b""
    metadata = header + (tail if isinstance(tail, bytes) and not re.match(rb"\d+\s+\(", tail) else b"")
    ids, sizes = UID.findall(metadata), SIZE.findall(metadata)
    if (len(ids) != 1 or len(sizes) != 1 or int(ids[0]) != uid
            or not 0 < len(raw) <= MAX_MESSAGE_BYTES or int(sizes[0]) != len(raw)):
        return None
    return raw


def recent_messages(host, user, mailbox, method, credential, limit):
    with open_mailbox(host, user, mailbox, method, credential) as (client, count, validity):
        if not count:
            return
        status, rows = client.fetch(f"{max(count - limit + 1, 1)}:{count}", "(UID RFC822.SIZE)")
        if status != "OK":
            raise ValueError("Impossibile leggere l’elenco dei messaggi IMAP.")
        candidates = {}
        for row in rows:
            if isinstance(row, bytes) and (uid := UID.search(row)) and (size := SIZE.search(row)):
                candidates[int(uid[1])] = int(size[1])
        for uid in sorted(candidates, reverse=True)[:limit]:
            source = {"host": host, "user": user, "mailbox": mailbox, "uid_validity": validity, "uid": uid}
            raw = fetch_message(client, uid) if 0 < candidates[uid] <= MAX_MESSAGE_BYTES else None
            yield raw, source


def retrieve_message(source, method, credential):
    with open_mailbox(source["host"], source["user"], source["mailbox"], method, credential) as (client, _, validity):
        if validity != source["uid_validity"]:
            raise ValueError("La cartella IMAP è cambiata. Reimporta il messaggio prima di procedere.")
        raw = fetch_message(client, source["uid"])
        if raw is None:
            raise ValueError("Messaggio originale non disponibile nella cartella IMAP.")
        return raw
