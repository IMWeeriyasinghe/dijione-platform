"""Bounded Recruitment Source module (Data Ownership Architecture v2).

The DijiOne standard source-sync framework for the Lever provider — sync-run
state, single-flight, async ad-hoc + scheduled reconciliation, freshness.
Lives inside talent-api as a bounded namespace for now; the promotion path
is a lift into apps/recruitment-api (Architecture v2 SS10). No code outside
this package imports the Lever client directly."""
