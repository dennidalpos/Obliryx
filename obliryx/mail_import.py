from contextlib import closing
from time import sleep

from .analysis import MAX_MESSAGE_BYTES, analyze_email, has_unsubscribe, mail_match_pattern, severity


def read_eml(path):
    with path.open("rb") as stream:
        raw = stream.read(MAX_MESSAGE_BYTES + 1)
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ValueError("Messaggio superiore a 5 MiB.")
    return raw


def eml_messages(path):
    if path.is_dir():
        paths = sorted(item for item in path.iterdir() if item.is_file() and item.suffix.lower() == ".eml")
    elif path.is_file() and path.suffix.lower() == ".eml":
        paths = [path]
    else:
        raise ValueError("Indica un file .eml o una cartella contenente file .eml.")
    for file in paths:
        try:
            yield read_eml(file)
        except (OSError, ValueError):
            yield None


def eml_snapshot(folder):
    snapshot = {}
    for file in folder.iterdir():
        if file.suffix.lower() != ".eml" or file.is_symlink() or not file.is_file():
            continue
        try:
            stat = file.stat()
        except FileNotFoundError:
            continue
        snapshot[file] = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    return snapshot


def watch_eml(store, folder, interval):
    if not folder.is_dir():
        raise ValueError("Indica una cartella locale di file .eml.")
    previous = eml_snapshot(folder)
    processed = {}
    while True:
        sleep(interval)
        current = eml_snapshot(folder)
        processed = {file: signature for file, signature in processed.items() if file in current}
        for file, signature in sorted(current.items()):
            if previous.get(file) != signature or processed.get(file) == signature:
                continue
            try:
                raw = read_eml(file)
                after = file.stat()
            except FileNotFoundError:
                continue
            except (ValueError, PermissionError):
                yield collect(store, (None,))
            else:
                current_signature = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                if current_signature != signature:
                    continue
                yield collect(store, (raw,))
            processed[file] = signature
        previous = current


def mbox_messages(path):
    with path.open("rb") as stream:
        first = stream.readline(MAX_MESSAGE_BYTES + 1)
        if not first:
            return
        if not first.startswith(b"From ") or not first.endswith(b"\n"):
            raise ValueError("Il file non inizia con un separatore MBOX valido.")
        buffer = bytearray()
        oversized = False
        starts_line = True
        while chunk := stream.readline(MAX_MESSAGE_BYTES + 3):
            ends_line = chunk.endswith(b"\n")
            if starts_line and ends_line and chunk.startswith(b"From "):
                yield None if oversized else finish_mbox_message(buffer)
                buffer.clear()
                oversized = False
            elif not oversized:
                if len(buffer) + len(chunk) > MAX_MESSAGE_BYTES + 2:
                    buffer.clear()
                    oversized = True
                else:
                    buffer.extend(chunk)
            starts_line = ends_line
        yield None if oversized else finish_mbox_message(buffer)


def finish_mbox_message(buffer):
    # The blank separator line is part of the container, not the original email.
    if buffer.endswith(b"\r\n\r\n"):
        del buffer[-2:]
    elif buffer.endswith(b"\n\n"):
        del buffer[-1:]
    return bytes(buffer) if 0 < len(buffer) <= MAX_MESSAGE_BYTES else None


def message_identities(raw):
    # MBOX exports and EML downloads may differ only in the line ending convention.
    canonical = raw.replace(b"\r\n", b"\n")
    variants = dict.fromkeys((canonical, raw, canonical.replace(b"\n", b"\r\n")))
    return [b"eml\x00" + variant for variant in variants]


def analyze_message(raw, pattern=None):
    if raw is None:
        return None, None
    try:
        return raw, analyze_email(raw, pattern)
    except (ValueError, TypeError, RecursionError):
        return None, None


def save_mail_record(store, raw, finding, source):
    identity, *legacy = message_identities(raw)
    if source:
        finding["imap_sources"] = [source]
    finding_id, created = store.save(finding, identity, alternate_identities=legacy)
    if source and not created:
        store.add_imap_source(finding_id, source)
    return finding_id, created


def collect_records(store, records):
    counts = dict(importati=0, duplicati=0, senza_indicatori=0, errori=0)
    for raw, source in records:
        raw, finding = analyze_message(raw)
        if raw is None:
            counts["errori"] += 1
            continue
        if finding is None:
            counts["senza_indicatori"] += 1
            continue
        _, created = save_mail_record(store, raw, finding, source)
        counts["importati" if created else "duplicati"] += 1
    return counts


def collect(store, messages):
    return collect_records(store, ((raw, None) for raw in messages))


def mail_source(path):
    return mbox_messages(path) if path.suffix.lower() == ".mbox" else eml_messages(path)


def scan_records(store, records, category, value):
    pattern = mail_match_pattern(category, value)
    counts = dict(importati=0, aggiornati=0, duplicati=0, senza_corrispondenze=0, errori=0)
    for raw, source in records:
        raw, finding = analyze_message(raw, pattern)
        if raw is None:
            counts["errori"] += 1
            continue
        fields = sorted(finding.pop("mail_match_fields")) if finding else []
        if not fields:
            counts["senza_corrispondenze"] += 1
            continue
        finding["data_types"] = [category]
        finding["mail_matches"] = {category: fields}
        finding_id, created = save_mail_record(store, raw, finding, source)
        if created:
            counts["importati"] += 1
        elif store.record_mail_match(finding_id, category, fields, finding["subject"]):
            counts["aggiornati"] += 1
        else:
            counts["duplicati"] += 1
    return counts


def scan_mail(store, path, category, value):
    with closing(mail_source(path)) as messages:
        return scan_records(store, ((raw, None) for raw in messages), category, value)


def find_original(store, finding_id, path):
    with closing(mail_source(path)) as messages:
        for raw in messages:
            if raw is not None and any(store.matches(finding_id, identity) for identity in message_identities(raw)):
                return raw
    raise ValueError("Il file originale non contiene il messaggio associato al riscontro.")


def campaign_summary(findings):
    groups = {}
    levels = {"bassa": 0, "media": 1, "alta": 2}
    for finding_id, finding in findings:
        if finding["source"] != "messaggio_importato" or not finding.get("indicators"):
            continue
        sender = finding["sender"]
        list_id = finding.get("list_id", "")
        # A missing or ambiguous sender is insufficient evidence to merge records.
        key = (sender, list_id.casefold()) if sender else (None, finding_id)
        level, _ = severity(finding)
        group = groups.setdefault(key, {
            "mittente_dichiarato": sender, "lista_dichiarata": list_id or None,
            "gravita_massima": level, "messaggi": 0, "non_riconosciute": 0,
            "senza_canale": 0, "riscontro_recente": finding_id,
        })
        group["messaggi"] += 1
        group["non_riconosciute"] += finding["enrollment"] == "non_riconosciuta"
        group["senza_canale"] += not has_unsubscribe(finding)
        if levels[level] > levels[group["gravita_massima"]]:
            group["gravita_massima"] = level
    return sorted(groups.values(), key=lambda item: levels[item["gravita_massima"]], reverse=True)
