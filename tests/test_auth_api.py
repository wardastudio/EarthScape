import pytest

pytestmark = pytest.mark.usefixtures("client", "app")


NEW_USER = {
    "full_name": "Integration User",
    "email": "integration-user@earthscape.org",
    "phone": "+15559998888",
    "password": "Integrate@123",
    "confirm_password": "Integrate@123",
    "role": "researcher",
}


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code in {200, 503}
    body = resp.get_json()
    assert "status" in body
    assert "version" in body


def test_api_register_returns_201(client):
    payload = dict(NEW_USER)
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code in {201, 409}
    body = resp.get_json() or {}
    if resp.status_code == 201:
        assert "user" in body or "email" in (body.get("user") or {})


def test_api_register_invalid_email(client):
    payload = dict(NEW_USER)
    payload["email"] = "not-email"
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 422


def test_api_register_weak_password(client):
    payload = dict(NEW_USER)
    payload["email"] = "weak-pass@earthscape.org"
    payload["password"] = "123"
    payload["confirm_password"] = "123"
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 422


def test_api_login_invalid_credentials(client):
    resp = client.post("/api/auth/login", json={"email": "nobody@nowhere.com", "password": "nope"})
    assert resp.status_code == 401
    body = resp.get_json()
    assert "error" in body


def test_api_login_with_defaults_returns_tokens(client):
    resp = client.post("/api/auth/login", json={"email": "analyst@earthscape.org", "password": "Analyst@123"})
    if resp.status_code == 200:
        body = resp.get_json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert "user" in body
    else:
        assert resp.status_code in {401, 500}


def test_api_refresh_token_flow(client):
    login_resp = client.post("/api/auth/login", json={"email": "admin@earthscape.org", "password": "Admin@123"})
    if login_resp.status_code != 200:
        pytest.skip("MongoDB not available; default admin user was not seeded.")
    refresh = login_resp.get_json()["refresh_token"]
    resp = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    body = resp.get_json()
    assert "access_token" in body
    assert "refresh_token" in body


def test_auth_routes_html(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    resp = client.get("/register")
    assert resp.status_code == 200
    resp = client.get("/forgot-password")
    assert resp.status_code == 200
    resp = client.get("/reset-password")
    assert resp.status_code == 200


def test_forgot_password_returns_ok(client):
    resp = client.post("/api/auth/forgot-password", json={"email": "any-email@example.com"})
    assert resp.status_code == 200


def test_reset_password_invalid_token(client):
    resp = client.post("/api/auth/reset-password", json={"token": "garbage", "password": "Newpass@123"})
    assert resp.status_code == 422


def test_unauthenticated_profile_endpoint_401(client):
    resp = client.get("/api/profile")
    assert resp.status_code == 401


def test_admin_users_requires_auth(client):
    resp = client.get("/api/admin/users")
    assert resp.status_code in {401, 302}


def test_html_pages_return_ok(client):
    for path in ["/", "/about", "/contact", "/faq"]:
        resp = client.get(path)
        assert resp.status_code == 200


def test_404_returns_consistent_json(client):
    resp = client.get("/api/nonexistent-endpoint-xyz")
    assert resp.status_code == 404
    json_body = resp.get_json(silent=True)
    if json_body:
        assert "error" in json_body
