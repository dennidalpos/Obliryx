"""Explicit interaction boundary shared by terminal and desktop services."""
import builtins
import getpass
import json
from contextlib import contextmanager
from contextvars import ContextVar


class TerminalInteraction:
    def ask(self, label, secret=False):
        return getpass.getpass(label) if secret else builtins.input(label)

    def emit(self, value):
        print(json.dumps(value, ensure_ascii=True, indent=2))

    def notify(self, message):
        print(message)

    def approve(self, value, message):
        self.emit(value)
        if self.ask(message + " Digita CONFERMO: ").strip() != "CONFERMO":
            raise ValueError("Azione annullata.")

    def check(self):
        pass

    def begin_effect(self):
        self.check()


current = ContextVar("obliryx_interaction", default=TerminalInteraction())


@contextmanager
def using(interaction):
    token = current.set(interaction)
    try:
        yield
    finally:
        current.reset(token)


def ask(label, secret=False):
    return current.get().ask(label, secret)


def checked(items):
    for item in items:
        current.get().check()
        yield item
