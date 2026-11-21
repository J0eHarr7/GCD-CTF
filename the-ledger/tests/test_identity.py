"""Act I — identity is not authority."""
from tests.conftest import ALICE, login


def test_login_and_whoami(client, alice):
    resp = client.get("/api/v1/auth", headers=alice)
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["id"] == "usr_alice"
    assert body["active_org"]["id"] == "org_helios"
    assert body["memberships"][0]["role"] == "analyst"


def test_login_rejects_bad_password(client):
    resp = client.post(
        "/api/v1/auth", json={"email": ALICE[0], "password": "wrong"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


def test_unauthenticated_and_malformed_are_denied(client):
    assert client.get("/api/v1/projects").status_code == 401
    assert client.get("/api/v1/projects", headers={"Authorization": "Basic x"}).status_code == 401
    assert (
        client.get("/api/v1/projects", headers={"Authorization": "Bearer nope"}).status_code
        == 401
    )


def test_logout_revokes_session(client, alice):
    assert client.delete("/api/v1/auth", headers=alice).status_code == 200
    assert client.get("/api/v1/auth", headers=alice).status_code == 401


def test_active_org_switch_is_not_membership_checked(client, alice):
    """A principal can point its session at an organisation it does not belong to."""
    resp = client.post(
        "/api/v1/sessions/switch",
        headers=alice,
        json={"organization_id": "org_vantage"},
    )
    assert resp.status_code == 200
    assert resp.json()["active_org"]["id"] == "org_vantage"
    assert resp.json()["previous_org_id"] == "org_helios"


def test_projects_are_scoped_by_membership(client, alice):
    """The projects endpoint ignores the session's active organisation."""
    before = client.get("/api/v1/projects", headers=alice).json()
    assert before["organization_id"] == "org_helios"
    client.post(
        "/api/v1/sessions/switch",
        headers=alice,
        json={"organization_id": "org_vantage"},
    )
    after = client.get("/api/v1/projects", headers=alice).json()
    assert after["organization_id"] == "org_helios"
    assert after["projects"] == before["projects"]


def test_assessments_are_scoped_by_active_org(client, alice):
    """The assessments endpoint follows the session's active organisation."""
    before = client.get("/api/v1/assessments", headers=alice).json()
    assert before["organization_id"] == "org_helios"
    assert all(a["org_id"] == "org_helios" for a in before["assessments"])

    client.post(
        "/api/v1/sessions/switch",
        headers=alice,
        json={"organization_id": "org_vantage"},
    )
    after = client.get("/api/v1/assessments", headers=alice).json()
    assert after["organization_id"] == "org_vantage"
    ids = {a["id"] for a in after["assessments"]}
    assert "asm_conf" in ids


def test_single_project_denies_cross_tenant(client, alice):
    client.post(
        "/api/v1/sessions/switch",
        headers=alice,
        json={"organization_id": "org_vantage"},
    )
    # Even with the active org pointed at Vantage, the authoritative project
    # lookup refuses.
    assert client.get("/api/v1/projects/prj_vantage_black", headers=alice).status_code == 404


def test_unknown_organization_switch_404(client, alice):
    resp = client.post(
        "/api/v1/sessions/switch",
        headers=alice,
        json={"organization_id": "org_nope"},
    )
    assert resp.status_code == 404
