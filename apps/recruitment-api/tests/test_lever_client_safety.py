"""Static/introspection safety checks — CLAUDE.md §60 LIVE LEVER SAFETY
CONTRACT: the real production client must have no code path capable of
issuing a write to Lever, and must never expose the API key.

Deliberately does not perform any live network call (no test in this repo
may touch the real Lever tenant automatically) — see the separately-run,
human-triggered manual sanity check in the implementation report instead.
"""

import inspect
from pathlib import Path

from app.integrations.lever.client import LeverClient
from app.integrations.lever.live_client import LiveLeverClient

_FORBIDDEN_WORDS = {"post", "put", "patch", "delete", "create", "update", "write"}


def test_live_lever_client_exposes_no_write_capable_method():
    public_methods = [
        name
        for name, _ in inspect.getmembers(LiveLeverClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    ]
    for name in public_methods:
        words = set(name.lower().split("_"))
        offending = words & _FORBIDDEN_WORDS
        assert not offending, (
            f"LiveLeverClient.{name} looks write-capable (word(s) {offending}) — "
            "Lever access must remain strictly read-only"
        )


def test_live_lever_client_implements_read_only_abstract_interface():
    abstract_methods = {
        name for name in dir(LeverClient) if not name.startswith("_")
    }
    for name in abstract_methods:
        assert name.startswith("list_") or name.startswith("get_"), (
            f"LeverClient.{name} is not a read-shaped method name"
        )


def test_live_lever_client_source_never_calls_write_http_verbs():
    source_path = Path(inspect.getfile(LiveLeverClient))
    source = source_path.read_text(encoding="utf-8")
    for forbidden_call in (".post(", ".put(", ".patch(", ".delete("):
        assert forbidden_call not in source, (
            f"live_client.py contains '{forbidden_call}' — Lever access must be GET-only"
        )


def test_live_lever_client_never_logs_the_raw_api_key():
    source_path = Path(inspect.getfile(LiveLeverClient))
    source = source_path.read_text(encoding="utf-8")
    # The only reference to the key must be constructing BasicAuth from
    # settings — never interpolated into a logger.* call or an f-string
    # that isn't the auth construction itself.
    for line in source.splitlines():
        if "logger." in line:
            assert "api_key" not in line and "self._auth" not in line
