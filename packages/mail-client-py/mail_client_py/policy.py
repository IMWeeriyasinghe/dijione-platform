"""Recipient policy — answers "are we allowed to send to this recipient",
kept deliberately separate from transport ("how do we send"). The library
ships the mechanism; each consuming service owns the actual allowlist
values (e.g. Birthday's own MAIL_ALLOWLIST config) — see
docs/platform/email-architecture.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum


class PolicyOutcome(StrEnum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    DISABLED = "DISABLED"


class MailPolicy(ABC):
    @abstractmethod
    def check(self, recipient: str) -> PolicyOutcome: ...


class DisabledPolicy(MailPolicy):
    """The safe default — always rejects, transport never invoked."""

    def check(self, recipient: str) -> PolicyOutcome:
        return PolicyOutcome.DISABLED


class InternalAllowlistPolicy(MailPolicy):
    """Rejects unless the recipient matches an explicit address (exact
    match) or domain (a bare ``@domain`` entry) in the configured list —
    the DEV-safe mode. A non-matching recipient is BLOCKED, never DISABLED
    — the transport itself is configured on, just this one recipient is
    rejected."""

    def __init__(self, allowlist: list[str]):
        self._exact = {a.strip().lower() for a in allowlist if a.strip() and not a.strip().startswith("@")}
        self._domains = {a.strip().lower() for a in allowlist if a.strip().startswith("@")}

    def check(self, recipient: str) -> PolicyOutcome:
        addr = (recipient or "").strip().lower()
        if not addr:
            return PolicyOutcome.BLOCKED
        if addr in self._exact:
            return PolicyOutcome.ALLOWED
        domain = addr.rsplit("@", 1)[-1] if "@" in addr else ""
        if domain and f"@{domain}" in self._domains:
            return PolicyOutcome.ALLOWED
        return PolicyOutcome.BLOCKED


class ProductionPolicy(MailPolicy):
    """Always accepts — only for a fully-live environment."""

    def check(self, recipient: str) -> PolicyOutcome:
        return PolicyOutcome.ALLOWED


def resolve_policy(name: str, *, allowlist: list[str] | None = None) -> MailPolicy:
    """Canonical unknown-policy behavior: an unrecognized/misconfigured
    name behaves identically to DisabledPolicy — never a silent
    pass-through."""
    if name == "internal_allowlist":
        return InternalAllowlistPolicy(allowlist or [])
    if name == "production":
        return ProductionPolicy()
    return DisabledPolicy()
