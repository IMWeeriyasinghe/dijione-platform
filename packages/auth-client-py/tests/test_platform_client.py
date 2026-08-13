from auth_client_py.platform_client import PlatformClient


def test_record_audit_event_is_non_fatal_when_platform_core_is_unreachable():
    # Port 1 is a reserved/unroutable port — this will always fail fast.
    client = PlatformClient(base_url="http://127.0.0.1:1", internal_secret="secret", timeout=0.5)
    ok = client.record_audit_event(actor_id=1, action="x", entity_type="Y", entity_id=1)
    assert ok is False


def test_notify_user_is_non_fatal_when_platform_core_is_unreachable():
    client = PlatformClient(base_url="http://127.0.0.1:1", internal_secret="secret", timeout=0.5)
    ok = client.notify_user(user_id=1, type="X", title="t")
    assert ok is False
