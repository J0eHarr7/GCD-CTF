"""Act II — the state machine and its flawed validator."""


def job(client, headers, assessment_id, action, reported_state=None):
    body = {"assessment_id": assessment_id, "action": action}
    if reported_state is not None:
        body["reported_state"] = reported_state
    return client.post("/api/v1/jobs", headers=headers, json=body)


def test_normal_lifecycle_from_draft(client, alice):
    assert job(client, alice, "asm_helios_net", "submit").status_code == 200
    assert job(client, alice, "asm_helios_net", "approve").status_code == 200
    assert job(client, alice, "asm_helios_net", "generate").status_code == 200
    assert job(client, alice, "asm_helios_net", "finalize").status_code == 200


def test_invalid_transition_is_rejected_without_reported_state(client, alice):
    # asm_helios_net is DRAFT; generate is only valid from APPROVED.
    resp = job(client, alice, "asm_helios_net", "generate")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "invalid_transition"


def test_unknown_action_is_rejected(client, alice):
    resp = job(client, alice, "asm_helios_net", "explode")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unknown_action"
    assert "valid_actions" in resp.json()["error"]["detail"]


def test_reported_state_bypasses_the_real_state(client, alice):
    """The validator evaluates the *reported* state, not the assessment's state."""
    client.post(
        "/api/v1/sessions/switch",
        headers=alice,
        json={"organization_id": "org_vantage"},
    )
    # asm_conf is READY. generate should be impossible. Asserting APPROVED
    # makes the validator happy.
    resp = job(client, alice, "asm_conf", "generate", reported_state="APPROVED")
    assert resp.status_code == 200
    body = resp.json()
    assert body["job"]["reported_state"] == "APPROVED"
    assert body["job"]["actual_state"] == "READY"


def test_wrong_reported_state_still_rejected(client, alice):
    client.post(
        "/api/v1/sessions/switch",
        headers=alice,
        json={"organization_id": "org_vantage"},
    )
    resp = job(client, alice, "asm_conf", "generate", reported_state="SUBMITTED")
    assert resp.status_code == 409


def test_repeated_action_is_idempotent(client, alice):
    first = job(client, alice, "asm_helios_web", "generate")
    assert first.status_code == 200 and first.json()["idempotent"] is False
    second = job(client, alice, "asm_helios_web", "generate")
    assert second.status_code == 200 and second.json()["idempotent"] is True

    # No duplicate events were emitted for the second call.
    events = client.get("/api/v1/events", headers=alice).json()["events"]
    gen_events = [
        e
        for e in events
        if e["assessment_id"] == "asm_helios_web"
        and e["type"] == "assessment.generate_requested"
    ]
    assert len(gen_events) == 1


def test_jobs_are_scoped_by_active_org(client, alice):
    before = client.get("/api/v1/jobs", headers=alice).json()
    assert before["organization_id"] == "org_helios"
    client.post(
        "/api/v1/sessions/switch",
        headers=alice,
        json={"organization_id": "org_vantage"},
    )
    after = client.get("/api/v1/jobs", headers=alice).json()
    assert after["organization_id"] == "org_vantage"
    assert any(j["id"] == "job_gen_nightfall" for j in after["jobs"])


def test_job_on_foreign_assessment_without_switch_is_404(client, alice):
    # Alice's active org is Helios, so a Vantage assessment does not exist for her.
    assert job(client, alice, "asm_conf", "finalize").status_code == 404
