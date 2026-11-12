import json
import re
from hashlib import sha256
from importlib.resources import files

from .analysis import address, https_url


def review_fingerprint(procedure):
    reviewed = {key: value for key, value in procedure.items() if key != "review_sha256"}
    canonical = json.dumps(reviewed, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def load_catalog():
    source = files("obliryx").joinpath("broker_procedures.json")
    catalog = json.loads(source.read_text(encoding="utf-8"))
    if catalog["schema"] != 1:
        raise ValueError("Schema del catalogo broker non supportato.")
    seen = set()
    for procedure in catalog["procedures"]:
        identifier = procedure["id"]
        channel = procedure["channel"]
        destination = channel["destination"]
        valid_destination = (address(destination) if channel["kind"] == "email"
                             else channel["kind"] == "web" and https_url(destination))
        if (identifier in seen or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", identifier)
                or not https_url(procedure["source"]) or not valid_destination
                or ("controller_source" in procedure and not https_url(procedure["controller_source"]))
                or procedure["support"] not in {"manuale", "assistito"}
                or procedure["license"] != "MIT" or not procedure["countries"]
                or any(country not in {"IT", "EU"} for country in procedure["countries"])):
            raise ValueError(f"Voce di catalogo non valida: {identifier}.")
        if procedure["review_sha256"] != review_fingerprint(procedure):
            raise ValueError(f"La procedura {identifier} è cambiata e richiede una nuova revisione.")
        seen.add(identifier)
    return catalog


def catalog_view(identifier=None):
    catalog = load_catalog()
    if identifier is None:
        return {
            "version": catalog["version"],
            "procedures": [
                {key: procedure[key] for key in ("id", "controller", "countries", "action", "support", "source")}
                for procedure in catalog["procedures"]
            ],
        }
    for procedure in catalog["procedures"]:
        if procedure["id"] == identifier:
            return {"version": catalog["version"], "holding_state": "unknown", **procedure}
    raise ValueError("Procedura del catalogo non trovata. Usa broker-catalog per elencare gli ID.")
