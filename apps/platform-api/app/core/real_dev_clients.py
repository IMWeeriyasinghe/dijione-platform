"""The real, currently-active DTC-tagged clients captured from a live,
GET-only Recruitment Source discovery run against the production Lever
tenant (Architecture Completion Plan real-data local validation,
2026-09-01). Companion to `app.core.permissions` — imported by both the
platform-api migration that seeds the canonical Client rows and
`scripts/seed.py`'s local-dev reseed path, so the two never drift, same
pattern the RBAC catalog already uses.

This is a **local-dev fixture snapshot**, not a live query — re-run the
discovery (`docs/integrations/lever.md`) and update this list by hand if
the real DTC tag set changes. Every name below is exactly what
`recruitment-api`'s `parse_dtc()` resolved with `status="OK"` from the real
`tags` field on a real Lever posting; nothing here is invented or
fuzzy-matched. Discovery run: 649 postings read, 32 carried a valid DTC
tag, 28 distinct client names, 0 malformed/ambiguous cases.

`public_id` is a deterministic slug of the name — stable, non-sequential
per Architecture Completion Plan §6.1, never reused for a different name.
`persona` marks the (small) subset also wired up as a DijiTalentFlow dev
login persona in `scripts/seed.py` — chosen as the clients with the most
real posting volume in the discovery run (2 each, vs. 1 for the rest), for
the most representative hands-on local demo; the other real clients still
exist as full canonical Client rows (visible in the Admin Center / TA
Portfolios), they are just not individually clickable in the dev persona
picker. Do not read the "persona" flag as "these are the only real
clients" — it is a UX/demo-practicality subset of a fully real set.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RealDevClient:
    name: str
    public_id: str
    persona: bool = False


REAL_DEV_CLIENTS: list[RealDevClient] = [
    RealDevClient("A1 Technology", "cli-a1-technology"),
    RealDevClient("ASI Solutions", "cli-asi-solutions"),
    RealDevClient("Access4", "cli-access4"),
    RealDevClient("Accucom", "cli-accucom"),
    RealDevClient("Affinity Nursing", "cli-affinity-nursing"),
    RealDevClient("Agent Maestro", "cli-agent-maestro"),
    RealDevClient("Andersen IT", "cli-andersen-it"),
    RealDevClient("Axiom IT", "cli-axiom-it"),
    RealDevClient("CMS group", "cli-cms-group", persona=True),
    RealDevClient("Computit", "cli-computit"),
    RealDevClient("Crofti", "cli-crofti"),
    RealDevClient("Databl.io", "cli-databl-io", persona=True),
    RealDevClient("EasyIT", "cli-easyit"),
    RealDevClient("Enject", "cli-enject"),
    RealDevClient("Intellium", "cli-intellium"),
    RealDevClient("Mobon", "cli-mobon"),
    RealDevClient("P1 Technologies", "cli-p1-technologies"),
    RealDevClient("PKCG", "cli-pkcg"),
    RealDevClient("Portal Technology", "cli-portal-technology", persona=True),
    RealDevClient("Sarj", "cli-sarj"),
    RealDevClient("Simple Biz", "cli-simple-biz"),
    RealDevClient("Stamp Loyalty", "cli-stamp-loyalty"),
    RealDevClient("StepFWD IT", "cli-stepfwd-it"),
    RealDevClient("Teba", "cli-teba"),
    RealDevClient("Tekspace Pty Ltd", "cli-tekspace-pty-ltd"),
    RealDevClient("The Living Co", "cli-the-living-co"),
    RealDevClient("The Podcast Boss", "cli-the-podcast-boss"),
    RealDevClient("XEN", "cli-xen"),
]

# public_ids of the pre-Architecture-Completion-Plan demo clients this
# real set replaces — reconciled away (rows + their dependent scope/role/
# crosswalk rows) by the migration and re-seeded persona logic below.
DEMO_CLIENT_PUBLIC_IDS: list[str] = [
    "cli-abc-company",
    "cli-xyz-company",
    "cli-nova-solutions",
]

PERSONA_CLIENTS: list[RealDevClient] = [c for c in REAL_DEV_CLIENTS if c.persona]
