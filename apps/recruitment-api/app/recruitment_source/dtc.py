"""Governed Lever posting-tag → client identifier parser.

Provider fact only — no DB, no DijiOne client concept. Parsing a governed
provider tag is a Recruitment Source responsibility; resolving it to a
canonical DijiOne Client and deciding trust/visibility is TalentFlow's
(see app/services/posting_client_mapping_reconciler.py).

The business convention (agreed with the TA team, entered by TA when
managing a Lever posting):

    DTC - <Client Name>          e.g. "DTC - Agent Maestro", "DTC - Crofti"

This is NOT arbitrary inference from Lever text. Only this exact governed
prefix is eligible; every ambiguous/malformed case must fail closed
downstream. No fuzzy matching, ever.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

# "DTC" (any case) + optional spaces + "-" + optional spaces, at the start.
_DTC_PREFIX_RE = re.compile(r"^\s*DTC\s*-\s*", re.IGNORECASE)
# A tag that starts with the DTC token at all (even if malformed after it).
_DTC_TOKEN_RE = re.compile(r"^\s*DTC\b", re.IGNORECASE)


class DtcParseStatus(StrEnum):
    NO_TAG = "NO_TAG"
    OK = "OK"
    MALFORMED = "MALFORMED"
    MULTIPLE = "MULTIPLE"


@dataclass(frozen=True)
class DtcParseResult:
    status: DtcParseStatus
    client_name: str | None = None
    raw_tag: str | None = None
    raw_tags: tuple[str, ...] = ()  # populated for MULTIPLE / MALFORMED diagnostics


def _is_dtc_tag(tag: str) -> bool:
    return bool(_DTC_TOKEN_RE.match(tag or ""))


def parse_dtc(tags: list[str] | None) -> DtcParseResult:
    """Extract the governed client identifier from a Lever posting's tags.

    - NO_TAG    : no tag begins with the DTC token
    - MALFORMED : a DTC tag exists but has no client part after "DTC -"
    - MULTIPLE  : more than one DTC tag (never guess — fail closed)
    - OK        : exactly one well-formed DTC tag; ``client_name`` is the
                  trimmed text after "DTC -", original case preserved
    """
    dtc_tags = [t for t in (tags or []) if isinstance(t, str) and _is_dtc_tag(t)]

    if not dtc_tags:
        return DtcParseResult(status=DtcParseStatus.NO_TAG)

    if len(dtc_tags) > 1:
        return DtcParseResult(
            status=DtcParseStatus.MULTIPLE, raw_tags=tuple(t.strip() for t in dtc_tags)
        )

    raw = dtc_tags[0].strip()
    m = _DTC_PREFIX_RE.match(raw)
    if m is None:
        # e.g. "DTC", "DTCsomething" — token present but no "-" separator
        return DtcParseResult(status=DtcParseStatus.MALFORMED, raw_tag=raw, raw_tags=(raw,))

    client_name = raw[m.end():].strip()
    if not client_name:
        # "DTC -", "DTC -    "
        return DtcParseResult(status=DtcParseStatus.MALFORMED, raw_tag=raw, raw_tags=(raw,))

    return DtcParseResult(status=DtcParseStatus.OK, client_name=client_name, raw_tag=raw)
