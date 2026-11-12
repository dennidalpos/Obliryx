import re
import unicodedata
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .store import now

MAX_MESSAGE_BYTES = 5 * 1024 * 1024
ADDRESS = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}\Z")
HOST = re.compile(r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
UNSUBSCRIBE = re.compile(r"unsubscribe|\bopt[ -]?out\b|disiscri|annulla\s+(?:l['’])?iscrizione|rimuovi\s+iscrizione", re.I)
INLINE_URL = re.compile(r"https://[^\s<>\"']+")
LIST_URIS = re.compile(r"\s*<[^<>\s]+>(?:\s*,\s*<[^<>\s]+>)*\s*\Z")
MARKETING = re.compile(r"newsletter|promozion|offerta|marketing|sconto|special offer", re.I)
DATA_TYPES = {"email", "nome", "username", "telefono", "indirizzo", "documento", "finanziari", "salute", "credenziali"}
INVISIBLE_HTML = {"script", "style", "template", "head", "noscript"}


def address(value):
    return value if len(value) <= 254 and ADDRESS.fullmatch(value) else None


def https_url(value):
    if not value or len(value) > 4096 or re.search(r"[^\x21-\x7e]|[\\<>\"#]", value):
        return None
    try:
        url = urlsplit(value)
        if url.scheme == "https" and url.hostname and HOST.fullmatch(url.hostname):
            if url.netloc.lower() == url.hostname and not url.fragment:
                return value
    except ValueError:
        pass
    return None


def normalized(text):
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def mail_match_pattern(category, value):
    literal = re.escape(normalized(value))
    if category == "email":
        return re.compile(r"(?<![\w@.!#$%&'*+/=?^`{|}~-])" + literal + r"(?![\w@+-]|\.[\w])")
    return re.compile(r"(?<!\w)" + literal + r"(?!\w)")


class UnsubscribeLinks(HTMLParser):
    def __init__(self, *, capture_text=False):
        super().__init__(convert_charrefs=True)
        self.current = None
        self.label = []
        self.urls = []
        self.hidden = []
        self.text = [] if capture_text else None

    def handle_starttag(self, tag, attrs):
        if tag in INVISIBLE_HTML:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "a":
            self.current = https_url(dict(attrs).get("href"))
            self.label = []

    def handle_data(self, data):
        if self.hidden:
            return
        if self.text is not None:
            self.text.append(data)
        if self.current:
            self.label.append(data)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
            return
        if tag == "a" and self.current:
            if UNSUBSCRIBE.search(" ".join(self.label)):
                self.urls.append(self.current)
            self.current = None


def text_parts(message):
    if message.get_content_disposition() == "attachment":
        return
    if message.get_content_maintype() == "multipart":
        for part in message.iter_parts():
            yield from text_parts(part)
    elif message.get_content_type() in ("text/html", "text/plain"):
        yield message


def analyze_email(raw, pattern=None):
    message = BytesParser(policy=policy.default).parsebytes(raw)
    sender = message.get("From")
    senders = getattr(sender, "addresses", ())
    sender_address = address(senders[0].addr_spec) if len(senders) == 1 else None
    subject = str(message.get("Subject", ""))[:300]
    matches = []
    if pattern and pattern.search(normalized(subject)):
        matches.append("oggetto")
    list_id = str(message.get("List-Id", ""))[:250]
    header = message.get_all("List-Unsubscribe", [])
    post = message.get_all("List-Unsubscribe-Post", [])
    routes = []
    header_value = str(header[0]) if len(header) == 1 else ""
    values = re.findall(r"<([^<>]+)>", header_value)
    for value in values[:12]:
        if url := https_url(value):
            routes.append({"kind": "web_header", "value": url})
        elif value.lower().startswith("mailto:"):
            mailbox = value[7:].partition("?")[0]
            if address(mailbox):
                # Retain the original URI for the required subject/body of RFC 2369.
                if len(value) <= 4096 and not re.search(r"[^\x21-\x7e]|[\\<>\"#]", value):
                    routes.append({"kind": "email_header", "value": value})
    web = [item for item in routes if item["kind"] == "web_header"]
    if (len(web) == 1 and LIST_URIS.fullmatch(header_value)
            and sum(value.lower().startswith(("http:", "https:")) for value in values) == 1
            and len(post) == 1 and str(post[0]).strip() == "List-Unsubscribe=One-Click"):
        web[0]["kind"] = "one_click_candidate"

    indicators = []
    for part in text_parts(message):
        try:
            content = part.get_content()[:200_000]
        except (LookupError, UnicodeError, ValueError):
            continue
        if not isinstance(content, str):
            continue
        if UNSUBSCRIBE.search(content) and "testo di disiscrizione" not in indicators:
            indicators.append("testo di disiscrizione")
        if part.get_content_type() == "text/html":
            parser = UnsubscribeLinks(capture_text=pattern is not None)
            try:
                parser.feed(content)
            except (AssertionError, ValueError):
                continue
            urls = parser.urls
            if pattern and pattern.search(normalized(" ".join(parser.text))) and "corpo_html" not in matches:
                matches.append("corpo_html")
        else:
            urls = [url for line in content.splitlines() if UNSUBSCRIBE.search(INLINE_URL.sub("", line))
                    for candidate in INLINE_URL.findall(line) if (url := https_url(candidate))]
            if pattern and pattern.search(normalized(content)) and "corpo_testuale" not in matches:
                matches.append("corpo_testuale")
        for url in urls:
            if len(routes) >= 12:
                break
            if all(route["value"] != url for route in routes):
                routes.append({"kind": "web_body", "value": url})
    if list_id:
        indicators.append("intestazione List-Id")
    if header:
        indicators.append("intestazione List-Unsubscribe")
    if MARKETING.search(subject):
        indicators.append("oggetto compatibile con marketing")
    if not indicators and not matches:
        return None
    finding = {
        "source": "messaggio_importato", "recorded_at": now(), "sender": sender_address,
        "list_id": list_id, "subject": subject, "message_date": str(message.get("Date", ""))[:120],
        "indicators": indicators, "data_types": [], "routes": routes,
        "enrollment": "da_verificare", "acquisition": "ignota", "evidence": "",
    }
    if pattern:
        finding["mail_match_fields"] = matches
        if "oggetto" in matches:
            finding["subject"] = "[oggetto omesso perché contiene il dato cercato]"
    return finding


def has_unsubscribe(finding):
    return any(route["kind"] != "privacy_candidate"
               and (route["kind"] != "unsubscribe_candidate" or route.get("confirmed_at"))
               for route in finding["routes"])


def severity(finding):
    types = set(finding["data_types"])
    route_available = has_unsubscribe(finding)
    if types & {"documento", "finanziari", "salute", "credenziali"}:
        return "alta", "Categorie sensibili o ad alto impatto indicate nel riscontro."
    if finding["acquisition"] == "acquisto_documentato":
        if not route_available:
            return "alta", "Acquisto documentato dall’utente e nessun canale di disiscrizione individuato."
        return "media", "Acquisto documentato dall’utente con un canale di disiscrizione individuato."
    if finding["source"] == "hibp":
        return "media", "HIBP associa l’indirizzo a una raccolta. Le altre categorie riguardano l’intero incidente."
    if not route_available and (types or finding["enrollment"] == "non_riconosciuta"):
        return "media", "Esposizione o iscrizione da approfondire, senza canale di disiscrizione individuato."
    if finding["enrollment"] == "non_riconosciuta" or types:
        return "media", "Iscrizione non riconosciuta o presenza di dati personali segnalata."
    return "bassa", "Indicatori di mailing list o marketing, con iscrizione da valutare."
