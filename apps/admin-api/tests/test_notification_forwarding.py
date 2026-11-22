"""admin-api forwards the Notifications recipient search unchanged with the caller's own token."""

HEADERS = {"Authorization": "Bearer valid-admin-token"}


def test_recipient_search_is_forwarded(api_client):
    resp = api_client.get("/api/admin/notifications/recipients", params={"q": "mad"}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    echo = resp.json()[0]
    assert echo["method"] == "GET" and echo["path"] == "/api/platform/admin/notifications/recipients"
    assert echo["query"] == {"q": "mad"}


def test_recipient_search_validates_length_locally(api_client):
    assert api_client.get("/api/admin/notifications/recipients", params={"q": "m"}, headers=HEADERS).status_code == 422
    assert api_client.get("/api/admin/notifications/recipients",
                          params={"q": "x" * 65}, headers=HEADERS).status_code == 422


def test_missing_token_is_refused_locally(api_client):
    assert api_client.get("/api/admin/notifications/recipients", params={"q": "mad"}).status_code == 401
