"""Recruitment Source domain internals owned by recruitment-api.

``dtc.py`` is the governed Lever posting-tag parser — a pure provider-fact
function (no DB, no DijiOne client concept). It is exposed on the canonical
posting DTO; resolving that fact to a DijiOne Client and deciding trust is
DijiTalentFlow's responsibility, not this service's.
"""
