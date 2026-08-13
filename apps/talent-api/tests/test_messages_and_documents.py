"""Messages and documents capture the sender/uploader's display name at
write time (``Message.sender_name`` / ``Document.uploaded_by_name``) instead
of resolving it via a cross-service lookup on every read, since User lives
in platform-api's own database now — see app/models/message.py."""

from app.schemas.talent_request import TalentRequestCreate
from app.services.talent_request_service import TalentRequestService


def _create_request(db, two_tenant_world):
    service = TalentRequestService(db)
    request = service.create_request(
        client_id=two_tenant_world["abc"].id, created_by=two_tenant_world["abc_user_id"],
        payload=TalentRequestCreate(designation="Role", description="d", required_skills=[]),
    )
    db.commit()
    return request


def test_send_and_list_messages_captures_sender_name(api_client, db, two_tenant_world):
    request = _create_request(db, two_tenant_world)
    headers = two_tenant_world["abc_headers"]

    resp = api_client.post(
        f"/api/talent/requests/{request.id}/messages", headers=headers, json={"body": "Hello TA team"}
    )
    assert resp.status_code == 201, resp.text
    message = resp.json()
    assert message["sender_name"] == "ABC Client User"
    assert message["sender_role"] == "TALENT_CLIENT"

    resp = api_client.get(f"/api/talent/requests/{request.id}/messages", headers=headers)
    assert resp.status_code == 200
    assert resp.json()[0]["sender_name"] == "ABC Client User"


def test_upload_and_list_documents_captures_uploader_name(api_client, db, two_tenant_world):
    request = _create_request(db, two_tenant_world)
    headers = two_tenant_world["ta_headers"]

    resp = api_client.post(
        f"/api/talent/requests/{request.id}/documents",
        headers=headers,
        json={"talent_request_id": request.id, "file_name": "CV.pdf", "category": "CV"},
    )
    assert resp.status_code == 201, resp.text
    document = resp.json()
    assert document["uploaded_by_name"] == "TA User"
    assert document["file_name"] == "CV.pdf"

    resp = api_client.get(f"/api/talent/requests/{request.id}/documents", headers=headers)
    assert resp.status_code == 200
    assert resp.json()[0]["uploaded_by_name"] == "TA User"


def test_staff_message_notifies_client(api_client, db, two_tenant_world, platform_calls):
    request = _create_request(db, two_tenant_world)

    resp = api_client.post(
        f"/api/talent/requests/{request.id}/messages",
        headers=two_tenant_world["ta_headers"],
        json={"body": "Update from the TA team"},
    )
    assert resp.status_code == 201
    assert any(
        b["role"] == "TALENT_CLIENT" and b["type"] == "NEW_MESSAGE" for b in platform_calls["broadcasts"]
    )
