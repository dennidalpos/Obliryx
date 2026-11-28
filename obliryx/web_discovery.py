"""Bounded public discovery. Search snippets are never evidence of a public match."""
import re
from urllib.parse import parse_qs, quote, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from .analysis import address, https_url, mail_match_pattern, normalized
from .network import DirectHTTPSConnection, resolve_destination
from .store import now

SEARCH_HOME = "https://duckduckgo.com/"
SEARCH_TERMS = "https://duckduckgo.com/terms"
SEARCH_POLICY = "https://duckduckgo.com/acceptable-use"
# The reviewed policy forbids displaying the service inside another service.
# A robots allow rule is not a grant of embedding/automation permission.
SEARCH_EMBEDDING_ALLOWED = False
SEARCH_POLICY_REVIEWED = "2026-11-13"
FIELDS = {"email": "Email", "phone": "Telefono", "name": "Nome e cognome",
          "username": "Username", "city": "Città"}


def identifiers(values):
    if not isinstance(values, dict) or set(values) - FIELDS.keys():
        raise ValueError("Dati di ricerca non validi.")
    result = {}
    for key in FIELDS:
        value = values.get(key, "")
        if not isinstance(value, str) or len(value) > 254 or any(ord(c) < 32 for c in value):
            raise ValueError("Controlla il campo " + FIELDS[key] + ".")
        value = " ".join(value.split())
        if value:
            result[key] = value
    if not any(k != "city" for k in result):
        raise ValueError("Inserisci almeno email, telefono, nome e cognome o username.")
    if result.get("email") and not address(result["email"]):
        raise ValueError("Inserisci un indirizzo email valido.")
    if result.get("phone") and not re.fullmatch(r"\+?[\d ()-]{5,32}", result["phone"]):
        raise ValueError("Inserisci un numero di telefono valido.")
    return result


def masked(value):
    if "@" in value:
        local, domain = value.rsplit("@", 1)
        return local[:1] + "•••@" + domain
    return value[:1] + "•••" + (value[-2:] if len(value) > 3 else "")


def queries(values):
    result = []
    for key, value in values.items():
        if key == "city":
            continue
        terms = [value]
        if key == "name":
            terms += [values.get("city") or values.get("username", "")]
        query = " ".join('"' + term.replace('"', '') + '"' for term in terms if term)
        result.append({"category": key, "label": FIELDS[key], "masked": masked(value),
                       "url": SEARCH_HOME + "?q=" + quote(query, safe="") + "&kl=it-it"})
    return result


def public_url(value):
    if not isinstance(value, str) or len(value) > 8192:
        raise ValueError("Collegamento non valido.")
    target = urlsplit(value)
    value = urlunsplit((target.scheme, target.netloc, target.path, target.query, ""))
    url = https_url(value)
    if not url:
        raise ValueError("È richiesto un collegamento HTTPS pubblico.")
    target = urlsplit(url)
    if target.port not in (None, 443) or target.username or target.password:
        raise ValueError("Destinazione non ammessa.")
    resolve_destination(target.hostname)
    return urlunsplit((target.scheme, target.netloc, target.path or "/", target.query, ""))


def read_public(url):
    url = public_url(url)
    target = urlsplit(url)
    connection = DirectHTTPSConnection(target.hostname, resolve_destination(target.hostname))
    try:
        connection.request("GET", target.path + ("?" + target.query if target.query else ""),
                           headers={"User-Agent": "Obliryx", "Accept": "text/plain,text/html"})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("Fonte non disponibile.")
        raw = response.read(512 * 1024 + 1)
        if len(raw) > 512 * 1024:
            raise ValueError("Fonte oltre il limite di lettura.")
        return raw.decode("utf-8", errors="replace")
    finally:
        connection.close()


def search_access(read=read_public):
    if not SEARCH_EMBEDDING_ALLOWED:
        return {"status": "unavailable", "reason": "La policy DuckDuckGo non consente di incorporare il servizio. Usa i link di ricerca nel browser esterno.",
                "policy_url": SEARCH_POLICY, "reviewed_on": SEARCH_POLICY_REVIEWED}
    try:
        robots = RobotFileParser()
        robots.parse(read(SEARCH_HOME + "robots.txt").splitlines())
        if not robots.can_fetch("Obliryx", SEARCH_HOME + "?q=example"):
            raise ValueError("Accesso automatico non disponibile.")
    except (OSError, ValueError):
        return {"status": "unavailable", "reason": "Impossibile verificare l’accesso automatico alla fonte."}
    return {"status": "available", "reason": "Accesso verificato per questa sessione."}


def candidate_links(links):
    seen, result = set(), []
    for item in links[:300]:
        value = item.get("url", "") if isinstance(item, dict) else ""
        try:
            target = urlsplit(value)
            if target.hostname in {"duckduckgo.com", "www.duckduckgo.com"}:
                value = parse_qs(target.query).get("uddg", [""])[0]
            target = urlsplit(value)
            value = urlunsplit((target.scheme, target.netloc, target.path or "/", target.query, ""))
            if (not https_url(value) or target.hostname in {"duckduckgo.com", "www.duckduckgo.com"}
                    or target.username or target.password or target.port not in (None, 443)):
                continue
            value = urlunsplit((target.scheme, target.netloc, target.path or "/", target.query, ""))
        except (ValueError, AttributeError, TypeError):
            continue
        if value not in seen:
            seen.add(value)
            result.append(value)
        if len(result) == 10:
            break
    return result


def match_page(snapshot, values):
    text = normalized(snapshot.get("text", "")[:200000])
    matches = []
    for key, value in values.items():
        if key == "city":
            continue
        if key == "phone":
            needle = re.sub(r"\D", "", value)
            pattern = r"(?<!\d)" + r"[ \t().-]*".join(re.escape(digit) for digit in needle) + r"(?!\d)"
            found = bool(needle and re.search(pattern, snapshot.get("text", "")))
        elif key == "email":
            found = bool(mail_match_pattern(key, value).search(text))
        else:
            needle = normalized(value)
            found = bool(re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", text))
        if found:
            matches.append({"category": key, "masked": masked(value)})
    blocked = snapshot.get("challenge") or snapshot.get("password")
    status = "blocked" if blocked else "unavailable" if snapshot.get("settled") is False else "observed" if matches else "not_observed"
    return {"status": status, "matches": matches if not blocked else [], "checked_at": now(),
            "identity": "Da verificare: la presenza del testo non identifica con certezza la persona.",
            "reason": "Verifica richiesta dal sito." if blocked else "Confronto con il testo visibile della pagina."}
