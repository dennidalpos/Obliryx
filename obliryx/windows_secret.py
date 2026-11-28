"""An application credential sealed for the current Windows user, never a password UI."""
import ctypes
import os
import secrets
from ctypes import wintypes


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(value, protect):
    if os.name != "nt":
        raise ValueError("L’apertura automatica richiede la protezione dell’account Windows.")
    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    function = crypt.CryptProtectData if protect else crypt.CryptUnprotectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    # CRYPTPROTECT_UI_FORBIDDEN; no machine-wide flag, no recovery in plaintext.
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ValueError("Windows non può aprire lo storico per questo account. Nessun file è stato sostituito.")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def application_password(directory, *, protect=None, unprotect=None):
    """Reserve the credential before SQLite creation; never replace an existing key."""
    protect = protect or (lambda data: _dpapi(data, True))
    unprotect = unprotect or (lambda data: _dpapi(data, False))
    directory.mkdir(parents=True, exist_ok=True)
    key_path = directory / "desktop-key.dpapi"
    database = directory / "desktop-history.sqlite3"
    if key_path.exists():
        try:
            password = unprotect(key_path.read_bytes()).decode("ascii")
        except (OSError, UnicodeError):
            raise ValueError("Credenziale locale non leggibile. Lo storico è stato conservato.") from None
        if len(password) != 64 or any(c not in "0123456789abcdef" for c in password):
            raise ValueError("Credenziale locale non valida. Lo storico è stato conservato.")
        return password
    if database.exists():
        raise ValueError("Manca la credenziale Windows dello storico. Nessun archivio è stato ricreato.")
    password = secrets.token_hex(32)
    sealed = protect(password.encode("ascii"))
    try:
        with key_path.open("xb") as handle:
            handle.write(sealed)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        return application_password(directory, protect=protect, unprotect=unprotect)
    return password
