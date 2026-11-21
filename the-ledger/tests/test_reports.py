"""Report access control — the authoritative rules, before any caching."""


def job(client, headers, assessment_id, action, reported_state=None):
    body = {"assessment_id": assessment_id, "action": action}
    if reported_state is not None:
        body["reported_state"] = reported_state
    return client.post("/api/v1/jobs", headers=headers, json=body)


def report_id_for(client, headers, assessment_id):
    assessments = client.get("/api/v1/assessments", headers=headers).json()
    for a in assessments["assessments"]:
        if a["id"] == assessment_id:
            return a["report_id"]
    raise AssertionError(f"{assessment_id} not visible")


def test_owner_can_read_own_report(client, alice):
    assert job(client, alice, "asm_helios_web", "generate").status_code == 200
    rid = report_id_for(client, alice, "asm_helios_web")
    assert rid is not None

    resp = client.get(f"/api/v1/reports/{rid}", headers=alice)
    assert resp.status_code == 200
    assert resp.json()["report"]["access"]["source"] == "computed"
    assert resp.json()["report"]["access"]["reason"] == "owner"

    assert job(client, alice, "asm_helios_web", "finalize").status_code == 200
    assert client.get(f"/api/v1/reports/{rid}", headers=alice).status_code == 200


def test_confidential_report_is_denied_to_analyst(client, carol):
    resp = client.get("/api/v1/reports/rep_conf_nightfall", headers=carol)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "report_access_denied"


def test_anonymous_is_denied(client):
    assert client.get("/api/v1/reports/rep_conf_nightfall").status_code == 401


def test_unknown_report_is_404(client, alice):
    assert client.get("/api/v1/reports/rep_nope", headers=alice).status_code == 404


def test_report_list_hides_the_confidential_report(client, alice, carol):
    helios = client.get("/api/v1/reports", headers=alice).json()["reports"]
    assert all(r["id"] != "rep_conf_nightfall" for r in helios)
    vantage = client.get("/api/v1/reports", headers=carol).json()["reports"]
    assert all(r["id"] != "rep_conf_nightfall" for r in vantage)


def test_delivery_requires_access(client, carol):
    resp = client.post(
        "/api/v1/reports/rep_conf_nightfall/deliveries",
        headers=carol,
        json={"recipient": "attacker@evil.example"},
    )
    assert resp.status_code == 403


def test_delivery_works_for_the_owner(client, alice):
    job(client, alice, "asm_helios_web", "generate")
    rid = report_id_for(client, alice, "asm_helios_web")
    resp = client.post(
        f"/api/v1/reports/{rid}/deliveries",
        headers=alice,
        json={"recipient": "alice@helios.example"},
    )
    assert resp.status_code == 200
    assert resp.json()["delivery"]["state"] == "SENT"
