"""Documented, unauthenticated public search APIs; no user API keys or billing.

GitHub searches public user profiles, not private data or authenticated code search.
Wikipedia searches the Italian encyclopedia, not the whole Web. Result snippets
are discarded; each candidate must still be checked at its source.
"""
import json
import http.client
import re
import threading
import time
from urllib.parse import quote, urlencode

from .network import DirectHTTPSConnection, resolve_destination
from .web_discovery import FIELDS, masked

USER_AGENT = "Obliryx/0.1 (+https://github.com/dennidalpos/Obliryx)"


class FreeSourceError(ValueError):
    pass


def public_json(host, path):
    if host not in {"api.github.com", "it.wikipedia.org"} or not path.startswith("/"):
        raise FreeSourceError("Fonte non ammessa.")
    connection = DirectHTTPSConnection(host, resolve_destination(host))
    try:
        connection.request("GET", path, headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                           **({"X-GitHub-Api-Version": "2026-03-10"} if host == "api.github.com" else {})})
        response = connection.getresponse()
        if response.status in {403, 429}:
            raise FreeSourceError("Limite di consultazione o accesso negato dalla fonte. Nessun tentativo automatico aggiuntivo.")
        if response.status != 200:
            raise FreeSourceError("Fonte non disponibile in questa sessione.")
        raw = response.read(512 * 1024 + 1)
        if len(raw) > 512 * 1024:
            raise FreeSourceError("Risposta della fonte oltre il limite di lettura.")
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get("error"):
            raise FreeSourceError("Risposta della fonte non utilizzabile.")
        return result
    except (OSError, ValueError, http.client.HTTPException) as exc:
        if isinstance(exc, FreeSourceError):
            raise
        raise FreeSourceError("Fonte non disponibile o risposta non leggibile.") from None
    finally:
        connection.close()


class FreeSources:
    def __init__(self, request=public_json, clock=time.monotonic):
        self.request, self.clock = request, clock
        self._next = {}
        self._mutex = threading.Lock()

    def specs(self, values):
        result = []
        for category, value in values.items():
            if category == "city":
                continue
            term = '"' + value.replace('"', '').replace('\\', '') + '"'
            if category in {"email", "name", "username"}:
                query = term + {"email":" in:email", "name":" in:fullname", "username":" in:login"}[category] + " type:user"
                if category == "name" and values.get("city"):
                    query += ' location:"' + values["city"].replace('"', '') + '"'
                result.append({"provider":"github", "title":"GitHub · profili pubblici · " + FIELDS[category],
                    "masked":masked(value), "host":"api.github.com",
                    "path":"/search/users?" + urlencode({"q":query,"per_page":5}),
                    "url":"https://github.com/search?" + urlencode({"q":query,"type":"users"})})
            # The city is used for name disambiguation on GitHub; encyclopedia
            # full text is searched with the literal identifier, then verified.
            result.append({"provider":"wikipedia", "title":"Wikipedia italiana · " + FIELDS[category],
                "masked":masked(value), "host":"it.wikipedia.org",
                "path":"/w/api.php?" + urlencode({"action":"query","list":"search","srsearch":term,
                    "srlimit":5,"srprop":"","format":"json","formatversion":2,"maxlag":5}),
                "url":"https://it.wikipedia.org/w/index.php?" + urlencode({"search":term})})
        return result

    def search(self, spec, cancelled):
        provider = spec["provider"]
        interval = 7 if provider == "github" else 1.1
        with self._mutex:
            wait = max(0, self._next.get(provider, 0) - self.clock())
            self._next[provider] = self.clock() + wait + interval
        if cancelled.wait(wait):
            raise FreeSourceError("Consultazione annullata.")
        data = self.request(spec["host"], spec["path"])
        if provider == "github":
            rows = data.get("items")
            if not isinstance(rows, list) or not isinstance(data.get("total_count"), int):
                raise FreeSourceError("Formato dei risultati GitHub inatteso.")
            links = []
            for row in rows[:5]:
                if not isinstance(row, dict):
                    raise FreeSourceError("Formato dei risultati GitHub inatteso.")
                login = row.get("login", "")
                if isinstance(login, str) and re.fullmatch(r"[a-zA-Z0-9-]{1,39}", login):
                    links.append("https://github.com/" + login)
            limited = bool(data.get("incomplete_results")) or data["total_count"] > 5
        else:
            query = data.get("query")
            rows = query.get("search") if isinstance(query, dict) else None
            if not isinstance(rows, list):
                raise FreeSourceError("Formato dei risultati Wikipedia inatteso.")
            links = []
            for row in rows[:5]:
                title = row.get("title") if isinstance(row, dict) else None
                if not isinstance(title, str):
                    raise FreeSourceError("Formato dei risultati Wikipedia inatteso.")
                links.append("https://it.wikipedia.org/wiki/" + quote(title.replace(" ", "_"), safe=""))
            limited = bool(data.get("continue"))
        return {"links":links, "status":"incomplete" if limited else "complete",
                "reason":("Consultazione limitata ai primi cinque candidati. " if limited else "Consultazione completata per questa fonte. ")
                         + ("I candidati richiedono verifica sulla pagina." if links else "Nessun candidato restituito; non è una prova di assenza dal Web.")}
