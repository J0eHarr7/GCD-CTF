"""The full intended chain, plus the negative cases that must fail.

Chain (Act I..Final):
  1. Point the session's active organisation at the other tenant.
  2. Discover the confidential assessment via the active-org-scoped listing.
  3. Run a `generate` job, bypassing the state machine with `reported_state`.
  4. The report service adopts the requester as owner (event trust), and a
     read seeds the access cache with an ALLOW.
  5. Finalize: ownership reverts to the authoritative owner, the state returns
     to READY — but the cached ALLOW survives.
  6. Read the report: the cached decision returns the final, flag-bearing body.
"""
from tests.conftest import ADMIN_KEY, TEST_FLAG


def login_headers(client, email, password):
    r = client.post("/api/v1/auth", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def job(client, headers, assessment_id, action, reported_state=None):
    body = {"assessment_id": assessment_id, "action": action}
    if reported_state is not None:
        body["reported_state"] = reported_state
    return client.post("/api/v1/jobs", headers=headers, json=body)


def report_id_for(client, headers, assessment_id):
    for a in client.get("/api/v1/assessments", headers=headers).json()["assessments"]:
        if a["id"] == assessment_id:
            return a["report_id"]
    raise AssertionError(f"{assessment_id} not visible")


def test_full_intended_chain(client, alice):
    # Act I — move the session into the other tenant.
    assert (
        client.post(
            "/api/v1/sessions/switch",
            headers=alice,
            json={"organization_id": "org_vantage"},
        ).status_code
        == 200
    )

    # Discover the confidential assessment through the active-org listing.
    assessments = client.get("/api/v1/assessments", headers=alice).json()
    ids = {a["id"] for a in assessments["assessments"]}
    assert "asm_conf" in ids
    rid = report_id_for(client, alice, "asm_conf")
    assert rid == "rep_conf_nightfall"

    # Before the chain, the report is inaccessible.
    assert client.get(f"/api/v1/reports/{rid}", headers=alice).status_code == 403

    # Act II — bypass the state machine.
    gen = job(client, alice, "asm_conf", "generate", reported_state="APPROVED")
    assert gen.status_code == 200

    # Act III — the report service adopts Alice as the draft owner.
    draft = client.get(f"/api/v1/reports/{rid}", headers=alice)
    assert draft.status_code == 200
    assert draft.json()["report"]["access"] == {
        "decision": "ALLOW",
        "source": "computed",
        "reason": "owner",
    }
    assert TEST_FLAG not in draft.json()["report"]["body"]  # still a draft

    # Act IV — finalize: ownership reverts to the real owner.
    assert job(client, alice, "asm_conf", "finalize").status_code == 200

    # Final — the stale cached ALLOW returns the READY body, flag included.
    final = client.get(f"/api/v1/reports/{rid}", headers=alice)
    assert final.status_code == 200
    report = final.json()["report"]
    assert report["access"]["source"] == "cache"
    assert report["state"] == "READY"
    assert TEST_FLAG in report["body"]


def test_chain_requires_seeding_the_cache(client, carol):
    """Skipping the intermediate read leaves no cached ALLOW, so it fails."""
    assert job(client, carol, "asm_conf", "generate", reported_state="APPROVED").status_code == 200
    assert job(client, carol, "asm_conf", "finalize").status_code == 200
    resp = client.get("/api/v1/reports/rep_conf_nightfall", headers=carol)
    assert resp.status_code == 403
    assert TEST_FLAG not in resp.text


def test_workflow_alone_does_not_reveal_the_flag(client, carol):
    """Generating only yields the redacted draft, never the final flag."""
    assert job(client, carol, "asm_conf", "generate", reported_state="APPROVED").status_code == 200
    resp = client.get("/api/v1/reports/rep_conf_nightfall", headers=carol)
    assert resp.status_code == 200
    report = resp.json()["report"]
    assert report["state"] == "GENERATING"
    assert TEST_FLAG not in report["body"]


def test_unrelated_requests_never_leak_the_flag(client, alice, carol):
    for headers in (alice, carol):
        for path in (
            "/api/v1/reports",
            "/api/v1/assessments",
            "/api/v1/jobs",
            "/api/v1/events",
            "/api/v1/audit",
            "/api/v1/deliveries",
        ):
            assert TEST_FLAG not in client.get(path, headers=headers).text


def test_repeated_full_chain_does_not_duplicate_state(client, alice):
    client.post(
        "/api/v1/sessions/switch",
        headers=alice,
        json={"organization_id": "org_vantage"},
    )
    first = job(client, alice, "asm_conf", "generate", reported_state="APPROVED")
    second = job(client, alice, "asm_conf", "generate", reported_state="APPROVED")
    assert first.status_code == 200
    assert second.json()["idempotent"] is True


def test_admin_reset_restores_the_fixture(client, alice):
    # Advance the world, then reset.
    client.post(
        "/api/v1/sessions/switch",
        headers=alice,
        json={"organization_id": "org_vantage"},
    )
    job(client, alice, "asm_conf", "generate", reported_state="APPROVED")
    client.get("/api/v1/reports/rep_conf_nightfall", headers=alice)

    resp = client.post("/api/v1/admin/reset", headers={"X-Admin-Key": ADMIN_KEY})
    assert resp.status_code == 200

    fresh = login_headers(client, "alice@helios.example", "alice-helios-2026")
    assert client.get("/api/v1/reports/rep_conf_nightfall", headers=fresh).status_code == 403


def test_admin_reset_rejects_wrong_key(client):
    assert (
        client.post("/api/v1/admin/reset", headers={"X-Admin-Key": "nope"}).status_code
        == 403
    )
