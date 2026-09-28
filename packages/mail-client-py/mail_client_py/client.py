"""MailClient — the one orchestration facade every consuming service
constructs from its own config (transport + policy + sender mailbox) and
calls `.send(...)` on, mirroring exactly how this repo's existing
`packages/auth-client-py` factories work (bind config once, at module load
time; expose a bound object, never a bare global).

Structurally guarantees "block before Graph": policy is checked before the
transport is ever invoked, so a call site cannot bypass the check by
forgetting one — the guarantee lives in this one code path, not in
caller discipline.
"""

from __future__ import annotations

from uuid import uuid4

from mail_client_py.policy import MailPolicy, PolicyOutcome
from mail_client_py.transport import MailOutcome, MailResult, MailTransport


class MailClient:
    def __init__(self, *, transport: MailTransport, policy: MailPolicy):
        self._transport = transport
        self._policy = policy

    @property
    def transport(self) -> MailTransport:
        return self._transport

    @property
    def policy(self) -> MailPolicy:
        return self._policy

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        correlation_id: str | None = None,
        content_type: str = "Text",
    ) -> MailResult:
        correlation_id = correlation_id or str(uuid4())

        policy_outcome = self._policy.check(to)
        if policy_outcome is PolicyOutcome.DISABLED:
            return MailResult(correlation_id=correlation_id, outcome=MailOutcome.DISABLED, sent=False)
        if policy_outcome is PolicyOutcome.BLOCKED:
            return MailResult(correlation_id=correlation_id, outcome=MailOutcome.BLOCKED, sent=False)

        # Sender is never taken from the caller — every MailTransport
        # implementation sends as its own configured mailbox only. There is
        # deliberately no `from`/`sender` parameter here to override.
        return self._transport.send(
            to=to, subject=subject, body=body, correlation_id=correlation_id, content_type=content_type
        )
