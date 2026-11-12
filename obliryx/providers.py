import hashlib
import http.client
import json
from urllib.parse import quote, urlencode

from .analysis import https_url

HIBP_HOST = "haveibeenpwned.com"
BRAVE_HOST = "api.search.brave.com"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def request_json(host, path, key_header, key, *, allow_not_found=False):
    if not key or not key.isascii() or any(not char.isprintable() or char.isspace() for char in key):
        raise ValueError("Chiave API mancante o non valida.")
    connection = http.client.HTTPSConnection(host, timeout=15)
    try:
        connection.request("GET", path, headers={"User-Agent": "Obliryx", "Accept": "application/json", key_header: key})
        response = connection.getresponse()
        if response.status == 404 and allow_not_found:
            return []
        if response.status == 429:
            wait = response.getheader("Retry-After", "")
            hint = f" Attendi {wait} secondi." if wait.isascii() and wait.isdecimal() and len(wait) <= 6 else ""
            raise ValueError(f"Limite di richieste raggiunto per {host}.{hint}")
        if response.status != 200:
            raise ValueError(f"{host} ha risposto HTTP {response.status}. Controlla piano o disponibilità.")
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ValueError(f"Risposta troppo grande da {host}.")
        return json.loads(data)
    except (OSError, http.client.HTTPException, json.JSONDecodeError, UnicodeError):
        raise ValueError(f"Connessione o risposta non valida da {host}.") from None
    finally:
        connection.close()


def breach_matches(email, key, method):
    if method == "prefisso":
        digest = hashlib.sha1(email.lower().encode()).hexdigest().upper()
        rows = request_json(HIBP_HOST, f"/api/v3/breachedaccount/range/{digest[:6]}", "hibp-api-key", key)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and str(row.get("hashSuffix", "")).upper() == digest[6:]:
                    names = row.get("websites")
                    if isinstance(names, list) and all(isinstance(name, str) and name for name in names):
                        return [{"Name": name} for name in names]
                    break
            else:
                return []
    else:
        path = "/api/v3/breachedAccount/" + quote(email, safe="") + "?truncateResponse=false"
        rows = request_json(HIBP_HOST, path, "hibp-api-key", key, allow_not_found=True)
        if isinstance(rows, list) and all(isinstance(row, dict) and isinstance(row.get("Name"), str)
                                          and row["Name"] for row in rows):
            return rows
    raise ValueError("Formato della risposta HIBP inatteso.")


def search_web(value, key):
    query = urlencode({"q": f'"{value}"', "country": "IT", "search_lang": "it", "count": 10,
                       "spellcheck": 0})
    result = request_json(BRAVE_HOST, "/res/v1/web/search?" + query, "X-Subscription-Token", key)
    if not isinstance(result, dict):
        raise ValueError("Formato della risposta Brave inatteso.")
    web = result.get("web") or {}
    rows = web.get("results", []) if isinstance(web, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Formato dei risultati Brave inatteso.")
    return [{"titolo": str(row.get("title", ""))[:250], "url": row["url"]}
            for row in rows[:10] if isinstance(row, dict) and isinstance(row.get("url"), str)
            and https_url(row["url"])]
