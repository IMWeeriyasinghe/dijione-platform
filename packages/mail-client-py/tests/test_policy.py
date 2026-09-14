from mail_client_py.policy import PolicyOutcome, resolve_policy


def test_disabled_policy_always_blocks():
    policy = resolve_policy("disabled")
    assert policy.check("anyone@example.com") == PolicyOutcome.DISABLED


def test_unrecognized_policy_name_behaves_as_disabled():
    policy = resolve_policy("totally-unknown-value")
    assert policy.check("anyone@example.com") == PolicyOutcome.DISABLED


def test_internal_allowlist_allows_exact_match_and_blocks_others():
    policy = resolve_policy("internal_allowlist", allowlist=["test.person@dijitalteam.com"])
    assert policy.check("test.person@dijitalteam.com") == PolicyOutcome.ALLOWED
    assert policy.check("someone.else@dijitalteam.com") == PolicyOutcome.BLOCKED
    assert policy.check("supplier@external.example.com") == PolicyOutcome.BLOCKED


def test_internal_allowlist_supports_domain_entries():
    policy = resolve_policy("internal_allowlist", allowlist=["@dijitalteam.com"])
    assert policy.check("anyone@dijitalteam.com") == PolicyOutcome.ALLOWED
    assert policy.check("anyone@external.example.com") == PolicyOutcome.BLOCKED


def test_production_policy_always_allows():
    policy = resolve_policy("production")
    assert policy.check("anyone@example.com") == PolicyOutcome.ALLOWED
