import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .analysis import INVISIBLE_HTML, https_url, normalized

UNSUBSCRIBE_BUTTON = re.compile(
    r"(?:unsubscribe(?: me)?|opt[ -]out|disiscriviti|annulla (?:l['’])?iscrizione|conferma disiscrizione)"
)
FIELD_NAME = re.compile(r"[A-Za-z0-9_.\[\]-]{1,128}")
OVERRIDES = {"form", "formaction", "formenctype", "formmethod", "formtarget", "formnovalidate"}


@dataclass(frozen=True)
class UnsubscribeForm:
    destination: str
    label: str
    fields: tuple[tuple[str, str | None], ...]

    def payload(self, email):
        return [(name, email if value is None else value) for name, value in self.fields]


class FormParser(HTMLParser):
    def __init__(self, page_url):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.forms = []
        self.active = None
        self.controls = []
        self.button = None
        self.hidden = []
        self.unsafe_document = False
        self.unsupported = False

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if (tag == "base" and "href" in attrs) or "form" in attrs:
            self.unsafe_document = True
        if tag in INVISIBLE_HTML:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "form":
            if self.active is not None:
                self.unsafe_document = True
                return
            self.active = attrs
            self.controls = []
            self.unsupported = len(attrs) != len(pairs)
        elif self.active is not None:
            if tag in {"select", "textarea", "fieldset", "object"}:
                self.unsupported = True
            if tag in {"input", "button"}:
                if len(attrs) != len(pairs) or OVERRIDES & attrs.keys() or any(k.startswith("on") for k in attrs):
                    self.unsupported = True
                if tag == "button":
                    if self.button is not None:
                        self.unsupported = True
                    self.button = (attrs, [])
                else:
                    self.controls.append((attrs.get("type") or "text", attrs, attrs.get("value") or ""))

    def handle_data(self, data):
        if self.button is not None and not self.hidden:
            self.button[1].append(data)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
            return
        if tag == "button" and self.button is not None:
            attrs, label = self.button
            self.controls.append((attrs.get("type") or "submit", attrs, " ".join(label)))
            self.button = None
        if tag == "form" and self.active is not None:
            if not self.unsupported and self.button is None:
                form = parse_form(self.page_url, self.active, self.controls)
                if form:
                    self.forms.append(form)
            self.active = None
            self.button = None


def parse_form(page_url, attrs, controls):
    if ((attrs.get("method") or "").lower() != "post" or "target" in attrs or "novalidate" in attrs
            or any(key.startswith("on") for key in attrs)
            or (attrs.get("accept-charset") or "utf-8").lower() != "utf-8"
            or (attrs.get("enctype") or "application/x-www-form-urlencoded").lower()
            != "application/x-www-form-urlencoded"):
        return None
    try:
        destination = https_url(urljoin(page_url, attrs.get("action") or ""))
    except ValueError:
        return None
    if not destination or urlsplit(destination).hostname != urlsplit(page_url).hostname:
        return None

    fields = []
    labels = []
    for kind, control, label in controls:
        if "disabled" in control:
            continue
        kind = kind.lower()
        if kind != "hidden" and "hidden" in control:
            return None
        name = control.get("name")
        value = control.get("value") or ""
        if kind == "submit":
            labels.append(normalized(label))
            if not name:
                continue
        if (not name or not FIELD_NAME.fullmatch(name) or name.lower() == "_charset_"
                or "dirname" in control or len(value) > 2048 or (value and not value.isprintable())):
            return None
        if kind == "email":
            if {"multiple", "readonly", "pattern", "minlength", "maxlength", "list"} & control.keys():
                return None
            fields.append((name, None))
        elif kind in {"hidden", "submit"}:
            fields.append((name, value))
        else:
            return None
    if len(labels) != 1 or not UNSUBSCRIBE_BUTTON.fullmatch(labels[0]):
        return None
    if not 1 <= len(fields) <= 8 or sum(value is None for _, value in fields) != 1:
        return None
    if len({name for name, _ in fields}) != len(fields):
        return None
    return UnsubscribeForm(destination, labels[0], tuple(fields))


def discover_unsubscribe_form(page_url, html):
    parser = FormParser(page_url)
    try:
        parser.feed(html)
        parser.close()
    except AssertionError:
        raise ValueError("Modulo HTML non analizzabile. Apri la procedura nel browser.") from None
    if parser.unsafe_document or len(parser.forms) != 1:
        raise ValueError("Modulo semplice e univoco non individuato. Apri la procedura nel browser.")
    return parser.forms[0]
