import http.client
import re
import ssl
from contextlib import closing
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
from urllib.parse import urlencode

from .network import DirectHTTPSConnection
from .site import MAX_PAGE_BYTES


SYNTHETIC_EMAIL = "reader@example.invalid"
START_PATH = "/demo/start"
SESSION_COOKIE = "obliryx_demo"
TOKEN = re.compile(r"[A-Za-z0-9_-]{16,96}")


@dataclass(frozen=True)
class Step:
    identifier: str
    path: str
    controls: tuple[tuple[str, str], ...]
    effect: str


PREPARE = Step("prepare", "/demo/prepare", (("email", "email"), ("csrf", "hidden")),
               "Prepara una richiesta dimostrativa con l’indirizzo sintetico.")
CONFIRM = Step("confirm", "/demo/confirm", (("request_id", "hidden"), ("csrf", "hidden")),
               "Conferma la richiesta dimostrativa preparata in questa sessione.")


def inspect_step(page, html, step):
    # Template content stays detached. Chrome never navigates to the site or receives its session cookie.
    form = page.evaluate("""({html, id}) => {
        const template = document.createElement("template");
        template.innerHTML = html;
        const root = template.content;
        if (root.querySelector("[data-assistance]")) return {assistance: true};
        const forms = root.querySelectorAll(`form#demo-${id}`);
        const form = forms[0];
        if (forms.length !== 1) return null;
        return {
            assistance: Boolean(form.querySelector("input[type=password], input[type=file]")),
            invalid: Boolean(root.querySelector("base, [form]") ||
                form.querySelector("[formaction], [formmethod], [formenctype], [formtarget], select, textarea")),
            procedure: form.dataset.procedure,
            effect: form.dataset.effect,
            action: form.getAttribute("action"),
            method: form.getAttribute("method"),
            controls: Array.from(form.querySelectorAll("input"), field => ({
                name: field.name, type: field.type, value: field.value, disabled: field.matches(":disabled")
            }))
        };
    }""", {"html": html, "id": step.identifier})
    if form and form["assistance"]:
        raise ValueError("Passaggio assistito richiesto. La sessione demo si ferma prima di trasmettere dati.")
    if (not form or form["invalid"] or form.get("procedure") != "obliryx-demo-v1"
            or form.get("effect") != step.identifier or form["action"] != step.path or form["method"] != "post"
            or tuple((field["name"], field["type"]) for field in form["controls"]) != step.controls
            or any(field["disabled"] for field in form["controls"])):
        raise ValueError("Il modulo è diverso dalla procedura revisionata. Nessun POST per questo passaggio.")
    values = []
    for field in form["controls"]:
        name, value = field["name"], field["value"]
        if name == "email" and not value:
            value = SYNTHETIC_EMAIL
        elif name == "email" or not TOKEN.fullmatch(value):
            raise ValueError("Il modulo contiene un valore non previsto dalla procedura.")
        values.append((name, value))
    return tuple(values)


def session_cookie(response):
    cookies = response.headers.get_all("Set-Cookie", [])
    if len(cookies) == 1:
        parsed = SimpleCookie()
        try:
            parsed.load(cookies[0])
        except CookieError:
            pass
        else:
            cookie = parsed.get(SESSION_COOKIE)
            if (len(parsed) == 1 and cookie and TOKEN.fullmatch(cookie.value)
                    and cookie["secure"] and cookie["httponly"] and cookie["samesite"].lower() == "strict"
                    and cookie["path"] == "/demo/" and not cookie["domain"]):
                return f"{SESSION_COOKIE}={cookie.value}"
    raise ValueError("Cookie di sessione demo mancante o non conforme.")


def exchange(connection, method, path, *, cookie=None, body=None, status=200):
    headers = {"Accept": "text/html", "User-Agent": "Obliryx"}
    if cookie is not None:
        headers["Cookie"] = cookie
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        if response.status != status:
            raise ValueError(f"Risposta inattesa dal sito controllato (HTTP {response.status}). "
                             "Verifica l’esito prima di ripetere il passaggio.")
        if cookie is not None and response.headers.get_all("Set-Cookie"):
            raise ValueError("Il sito ha cambiato il cookie della procedura. Verifica l’esito del passaggio.")
        if status == 204:
            response.read()
            return None
        if response.headers.get_content_type() != "text/html":
            raise ValueError("Il sito controllato non ha restituito il modulo HTML previsto.")
        data = response.read(MAX_PAGE_BYTES + 1)
        if len(data) > MAX_PAGE_BYTES:
            raise ValueError("Il modulo demo supera il limite di 1 MiB.")
        return data.decode("utf-8"), session_cookie(response) if cookie is None else cookie
    except (OSError, http.client.HTTPException):
        raise ValueError("Scambio HTTPS demo interrotto. Verifica l’esito prima di ripetere il passaggio.") from None


def approved_post(connection, origin, cookie, step, fields, approve, *, status=200):
    body = urlencode(fields).encode("ascii")
    visible = {name: value if name == "email" else "[valore di sessione]" for name, value in fields}
    approve({"metodo": "POST", "destinazione": origin + step.path, "campi": visible,
             "cookie": SESSION_COOKIE, "effetto": step.effect}, "Conferma questo passaggio sul sito di prova.")
    return exchange(connection, "POST", step.path, cookie=cookie, body=body, status=status)


def run_demo(port, ca_path, approve):
    if not 1 <= port <= 65535:
        raise ValueError("Porta HTTPS demo non valida.")
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except ImportError:
        raise ValueError("Installa l’extra demo e Chromium per eseguire l’adattatore di prova.") from None

    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    try:
        tls.load_verify_locations(cafile=str(ca_path))
    except (OSError, ssl.SSLError):
        raise ValueError("CA del sito di prova illeggibile o non valida.") from None
    origin = f"https://localhost:{port}"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(chromium_sandbox=True)
            try:
                context = browser.new_context(offline=True, java_script_enabled=False, service_workers="block",
                                              accept_downloads=False)
                try:
                    context.route("**/*", lambda route: route.abort())
                    context.route_web_socket("**/*", lambda socket: socket.close())
                    page = context.new_page()
                    with closing(DirectHTTPSConnection("localhost", "127.0.0.1", port=port, context=tls)) as connection:
                        approve({"metodo": "GET", "destinazione": origin + START_PATH,
                                 "effetto": "Apre una sessione sintetica sul sito di prova."},
                                "Conferma l’apertura della sessione demo.")
                        html, cookie = exchange(connection, "GET", START_PATH)
                        prepare = inspect_step(page, html, PREPARE)
                        html, _ = approved_post(connection, origin, cookie, PREPARE, prepare, approve)
                        confirm = inspect_step(page, html, CONFIRM)
                        approved_post(connection, origin, cookie, CONFIRM, confirm, approve, status=204)
                finally:
                    context.close()
            finally:
                browser.close()
    except PlaywrightError:
        raise ValueError("Browser demo non disponibile. Verifica l’installazione di Chromium.") from None
    return {"procedura": "obliryx-demo-v1", "stato": "confermata", "dati": "sintetici"}
