from email import policy
from email.parser import BytesParser

import dkim

from .analysis import address, header_routes
from .network import post_form

REQUIRED_HEADERS = {b"from", b"to", b"list-unsubscribe", b"list-unsubscribe-post"}


def verify_message(raw, sender, recipient, *, destination=None):
    message = BytesParser(policy=policy.default).parsebytes(raw, headersonly=True)
    for name in REQUIRED_HEADERS:
        if len(message.get_all(name.decode(), [])) != 1:
            raise ValueError("Intestazioni necessarie mancanti o duplicate.")
    recipients = [item.addr_spec for item in getattr(message["To"], "addresses", ())]
    if not sender or len(recipients) != 1 or not address(recipients[0]):
        raise ValueError("Il messaggio deve indicare un mittente e un destinatario univoci.")
    if recipients[0] != recipient:
        raise ValueError("L’indirizzo confermato non coincide con il destinatario del messaggio.")
    if destination is not None and {"kind": "one_click_candidate", "value": destination} not in header_routes(message):
        raise ValueError("La destinazione del riscontro non coincide con quella del messaggio originale.")
    domain = sender.rsplit("@", 1)[1].lower().encode()
    verifier = dkim.DKIM(raw, timeout=5)
    for index in range(min(len(message.get_all("DKIM-Signature", [])), 5)):
        try:
            signature, signed_headers, _ = verifier.verify_headerprep(index)
            if (signature and signature.get(b"d", b"").lower() == domain
                    and REQUIRED_HEADERS.issubset(signed_headers) and verifier.verify(index)):
                return
        except (dkim.DKIMException, ValueError, OSError):
            continue
    raise ValueError("Firma DKIM idonea non verificata. Usa il percorso assistito dopo aver controllato il mittente.")


def submit(url, ip):
    return post_form(url, ip, b"List-Unsubscribe=One-Click")
