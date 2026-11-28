import http.client
import re
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .analysis import INVISIBLE_HTML, UNSUBSCRIBE, https_url, normalized
from .network import DirectHTTPSConnection, resolve_destination

PRIVACY = re.compile(r"privacy|protezione dei dati|data protection|esercizio dei diritti", re.I)
MAX_PAGE_BYTES = 1024 * 1024


class Page(HTMLParser):
    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.hidden = []
        self.text = []
        self.href = None
        self.label = []
        self.routes = []
        self.password_gate = False

    def handle_starttag(self, tag, attrs):
        if tag in INVISIBLE_HTML:
            self.hidden.append(tag)
        if not self.hidden and tag == "a":
            self.href = dict(attrs).get("href")
            self.label = []
        if not self.hidden and tag == "input" and (dict(attrs).get("type") or "").lower() == "password":
            self.password_gate = True

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)
            if self.href:
                self.label.append(data)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
            return
        if tag != "a" or not self.href:
            return
        label = " ".join(self.label)
        kind = "unsubscribe_candidate" if UNSUBSCRIBE.search(label) else "privacy_candidate" if PRIVACY.search(label) else None
        if kind and len(self.routes) < 10:
            try:
                url = https_url(urljoin(self.url, self.href))
            except ValueError:
                url = None
            route = {"kind": kind, "value": url}
            if url and route not in self.routes:
                self.routes.append(route)
        self.href = None


def fetch_html(url, ip=None):
    if not https_url(url):
        raise ValueError("URL della pagina non valido.")
    target = urlsplit(url)
    path = target.path or "/"
    if target.query:
        path += "?" + target.query
    connection = DirectHTTPSConnection(target.hostname, ip or resolve_destination(target.hostname))
    try:
        connection.request("GET", path, headers={"User-Agent": "Obliryx", "Accept": "text/html"})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"Pagina non verificabile (HTTP {response.status}).")
        if response.headers.get_content_type() != "text/html":
            raise ValueError("La verifica riguarda pagine HTML accessibili direttamente.")
        raw = response.read(MAX_PAGE_BYTES + 1)
        if len(raw) > MAX_PAGE_BYTES:
            raise ValueError("La pagina supera il limite di 1 MiB.")
        return raw.decode(response.headers.get_content_charset("utf-8"), errors="replace")
    except ssl.SSLCertVerificationError:
        raise ValueError("Pagina non verificabile: certificato HTTPS non attendibile per Python.") from None
    except (OSError, LookupError, http.client.HTTPException, AssertionError):
        raise ValueError("Pagina non verificabile in questa sessione.") from None
    finally:
        connection.close()


def fetch_page(url):
    page = Page(url)
    try:
        page.feed(fetch_html(url))
    except AssertionError:
        raise ValueError("Pagina HTML non analizzabile.") from None
    return page


def inspect_page(url, value):
    if not normalized(value):
        raise ValueError("Valore di confronto non valido.")
    page = fetch_page(url)
    search = normalized(value)
    text = normalized(" ".join(page.text))
    found = re.search(r"(?<![\w@.])" + re.escape(search) + r"(?![\w@.])", text) is not None
    if not found and (not text or page.password_gate):
        raise ValueError("Pagina senza testo verificabile o protetta da accesso.")
    return found, page.routes


def discover_routes(url):
    if not https_url(url) or urlsplit(url).query:
        raise ValueError("Indica una pagina informativa HTTPS pubblica senza parametri personali.")
    return [{**route, "source_url": url} for route in fetch_page(url).routes]
