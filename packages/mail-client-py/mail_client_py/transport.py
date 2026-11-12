"""The shared, transport-agnostic mail contract every DijiOne service
consumes identically. Kept deliberately generic — no Birthday (or any
other app's) business meaning lives here; see docs/platform/email-architecture.md
for the full design.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum


class MailOutcome(StrEnum):
    """Truthful transport-level outcome of one send attempt. This is the
    ONLY place "did a real email leave the system" is answered — a
    consuming service's own business/workflow state (e.g. Birthday's
    ``SupplierCommunication.status``) is a separate, locally-owned concept
    that may choose to treat more than one outcome as "good enough to
    proceed," but that choice is never made in this shared library."""

    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    """Reserved for a caller that never reached MailClient.send() at all —
    never produced by MailClient itself."""
    DISABLED = "DISABLED"
    """The configured policy (or an unrecognized/misconfigured policy
    value — unknown always fails closed) rejected sending outright. The
    transport is never invoked."""
    BLOCKED = "BLOCKED"
    """The configured policy rejected this specific recipient. The
    transport is never invoked."""
    SIMULATED = "SIMULATED"
    """NullMailTransport executed the full mail flow, but no real email
    left the system. Never conflated with SUBMITTED."""
    SUBMITTED = "SUBMITTED"
    """A real transport (e.g. Microsoft Graph) accepted the send request.
    This means submitted, not delivered — Graph's 202 Accepted is not a
    delivery confirmation."""
    FAILED = "FAILED"
    """A real transport attempt was made and failed (auth, network, or a
    non-success response)."""


@dataclass(frozen=True)
class MailResult:
    """Returned by every MailClient.send() call, regardless of outcome —
    including BLOCKED/DISABLED/FAILED, so even a rejected/failed attempt
    stays traceable via correlation_id."""

    correlation_id: str
    outcome: MailOutcome
    # True ONLY when outcome == SUBMITTED. Never True for SIMULATED,
    # BLOCKED, DISABLED, or FAILED — a future consumer can trust
    # `sent == True` to mean a real transport genuinely submitted an
    # email. Prefer checking `.outcome` directly; `.sent` is a narrow
    # convenience for callers that only care whether a real send happened.
    sent: bool
    # Optional diagnostic metadata only (e.g. a Graph request-id header) —
    # never depended on as a business identifier.
    graph_request_id: str | None = None
    error: str | None = None


class MailTransport(ABC):
    """Implemented by NullMailTransport and GraphMailTransport. A
    transport never checks policy and never generates a correlation id —
    both are MailClient's job (client.py) — a transport's only
    responsibility is "given a recipient/subject/body/correlation id,
    actually attempt the send and report the truthful outcome."""

    @abstractmethod
    def send(self, *, to: str, subject: str, body: str, correlation_id: str) -> MailResult: ...
