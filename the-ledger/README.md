# THE LEDGER — Web / API CTF challenge

**Category:** Web (pure JSON API — no browser required)
**Difficulty:** Meduim
**Flag format:** `GCDxGLORY{...}`
**Objective:** Read the finalised assessment report **Project Nightfall**.

A multi-tenant assessment platform: organisations run projects, projects own
assessments, and approved assessments produce reports. You begin as an analyst
of one tenant and must end up holding a report that belongs to another.

The intended path threads **four independent flaws** together:

1. **Identity** — the session can be pointed at an organisation the user is not
   a member of, and one listing endpoint scopes by the session's active org
   while another scopes by the user's default org.
2. **State machine** — a job carries a caller-supplied `reported_state` and the
   transition validator evaluates the *reported* state instead of the real one.
3. **Internal trust** — the report service adopts the report owner from the
   workflow event on *generation*, but re-derives it from the authoritative
   assessment on *finalisation*.
4. **Stale decision** — the report-access cache stores ALLOW decisions and never
   invalidates them when ownership changes.

No single flaw reveals the flag; every one of them is load-bearing.

Dockerized, deterministic, black-box (the OpenAPI/docs endpoints are disabled),
and covered by a pytest suite that proves both the solve path and the decoys.

---

## 1. Run it

```bash
docker compose up --build
```

The API is at **http://localhost:8000** and speaks JSON only.

```bash
curl -s http://localhost:8000/api/v1/health
```

Set a real flag and admin key before an event by editing `FLAG` and `ADMIN_KEY`
in `compose.yaml`. If `FLAG` is unset the process generates a random one; if
`ADMIN_KEY` is unset the reset endpoint is disabled.

### Seeded accounts

| user | email | password | org | role |
|------|-------|----------|-----|------|
| Alice | `lina@helios.glory` | `lina-helios-2026` | Helios Audit Group | analyst |
| Erin  | `erin@helios.example`  | *(random, not distributed)* | Helios Audit Group | manager |
| Carol | `carol@vantage.example` | `carol-vantage-2026` | Vantage Confidential | analyst |
| Dave  | `dave@vantage.example`  | *(random, not distributed)* | Vantage Confidential | manager |

Alice and Carol are the two player-facing analysts (one per tenant). Erin and
Dave are managers whose passwords are generated at seed time and never
revealed; they exist so the data model has believable managers and so the
"manager can read any org report" rule is real.

### Seeded business objects

| assessment | org | state | classification |
|------------|-----|-------|----------------|
| `asm_helios_web` | Helios | APPROVED | INTERNAL |
| `asm_helios_net` | Helios | DRAFT | INTERNAL |
| `asm_vantage_api` | Vantage | SUBMITTED | CONFIDENTIAL |
| `asm_conf`      | Vantage | READY | TOP_SECRET |

The confidential assessment `asm_conf` ("Project Nightfall") already owns a
READY report, `rep_conf_nightfall`, whose owner is the manager `usr_dave` and
whose body contains the flag.

---

## 2. API

All routes are under `/api/v1`. Authentication is
`Authorization: Bearer <token>`.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/auth` | Log in, returns a session token |
| GET | `/auth` | Who am I (user, active org, memberships) |
| DELETE | `/auth` | Log out (revoke the current session) |
| GET | `/sessions` | List my sessions |
| POST | `/sessions/switch` | **Set the session's active organisation** (Act I) |
| GET | `/projects` | Projects — scoped by the user's **default** org |
| GET | `/projects/{id}` | Project detail |
| GET | `/assessments` | Assessments — scoped by the session's **active** org |
| GET | `/assessments/{id}` | Assessment detail |
| POST | `/jobs` | **Run a workflow action** on an assessment (Act II) |
| GET | `/jobs`, `/jobs/{id}` | Job history (scoped by active org) |
| GET | `/events` | Workflow events (scoped by active org) |
| GET | `/audit` | Audit records (scoped by active org) |
| POST | `/exports`, GET `/exports` | Dataset export queue |
| GET | `/reports` | Reports the caller may read (authoritative rules) |
| GET | `/reports/{id}` | **Final access gate** — returns the body (Acts III/IV) |
| POST | `/reports/{id}/deliveries` | Queue a delivery of a report |
| GET | `/deliveries` | My deliveries |
| POST | `/admin/reset` | Re-seed the world (`X-Admin-Key` header) |
| GET | `/health` | Liveness |

Workflow actions (the state machine):

```
submit   DRAFT       -> SUBMITTED
approve  SUBMITTED   -> APPROVED
generate APPROVED    -> GENERATING      (creates/adopts a report)
finalize GENERATING  -> READY           (finalises the report)
```

`POST /jobs` body: `{"assessment_id", "action", "reported_state"?}`.

---

## 3. The five concepts that must stay distinct

The challenge lives in the seams between these, so the code keeps them apart
and the writeup treats them as separate:

* **Principal** — the authenticated user (from the bearer token).
* **Membership** — `(user, org, role)`: analyst, manager, admin.
* **Active organisation** — the org the *session* is currently acting for.
  Security-relevant, and mutable via `/sessions/switch`.
* **Resource organisation** — the `org_id` recorded on an assessment, report or
  job. This, not the session, is what the resource actually belongs to.
* **Report owner** — a single **user**, derived differently on generation vs
  finalisation. This is what the access decision keys on.

---

## 4. Project layout

```
the-ledger/
├── app/
│   ├── __init__.py            # FastAPI app factory (docs disabled)
│   ├── __main__.py            # entrypoint: python -m app
│   ├── config.py              # env: DATABASE_URL, FLAG, ADMIN_KEY, TTL
│   ├── db.py                  # engine, session, create/clear
│   ├── errors.py              # uniform {error:{code,message,detail}} shape
│   ├── models.py              # schema (see the docstrings)
│   ├── security.py            # sessions, principals, password + id helpers
│   ├── serializers.py         # public JSON shapes
│   ├── seed.py                # deterministic fixture
│   ├── routers/               # identity, projects, workflow, audit, reports, admin, meta
│   └── services/
│       ├── workflow_service.py  # state machine + event bus   ← DEFECT 2
│       ├── report_service.py    # event consumer, render body  ← DEFECT 3
│       ├── access_cache.py      # ALLOW-only decision cache    ← DEFECT 4
│       └── audit.py
├── tests/                     # pytest
├── solve.sh                   # reference solver (cURL only)
├── WRITEUP.md                 # full solution walkthrough (organizers)
├── Dockerfile / compose.yaml
└── requirements.txt
```

### Where the four defects live

| Defect | Location |
|--------|----------|
| 1. Active-org switch has no membership check | `app/routers/identity.py` (`switch_active_org`) |
| 1. Listing scoping inconsistency | `app/routers/projects.py` (default org) vs `app/routers/workflow.py` (active org) |
| 2. Validator uses `reported_state` | `app/services/workflow_service.py` (`create_job`) |
| 3. Owner from event vs from assessment | `app/services/report_service.py` (`_generate` vs `_finalize`) |
| 4. ALLOW-only, never-invalidated cache | `app/services/access_cache.py` (`decision_for`) |

The shipped source contains **no** `VULN` markers. It reads like a young
platform whose report pipeline was migrated between two teams.

---

## 5. Run the tests

```bash
pip install -r requirements-dev.txt
pytest
```

31 tests across:

* `tests/test_identity.py` — login, sessions, the org switch, and the listing
  scoping seam.
* `tests/test_workflow.py` — the honest lifecycle, invalid transitions, the
  `reported_state` bypass, and idempotency.
* `tests/test_reports.py` — the authoritative access rules before any caching.
* `tests/test_full_chain.py` — the full chain returns the flag, and the
  negatives (cache must be seeded; workflow alone is not enough; no endpoint
  leaks the flag; reset restores the fixture).

---

## 6. Reference solve

```bash
./solve.sh http://localhost:8000
```

Expected output ends with the flag.

---

## 7. Flag handling

One flag per deployment, held server-side in `app/config.py::flag()`. It is
emitted by exactly one path: rendering the body of a report that is **READY**
to a caller the access decision **ALLOWs**.

* Set `FLAG` in the environment (see `compose.yaml`) for a fixed, reproducible
  flag during a scored event.
* Leave it unset and the process generates `GCDxGLORY{the_ledger_<16 hex>}`.
* The flag placeholder lives in the `rep_conf_nightfall` body as `{{FLAG}}` and
  is substituted only when the report state is `READY`. Reading the redacted
  draft, listing reports, or exporting data never reveals it.

---

## 8. Reset between teams

The world can be restored in place:

```bash
curl -s -X POST http://localhost:8000/api/v1/admin/reset \
     -H "X-Admin-Key: $ADMIN_KEY"
```

or, for a byte-identical fresh environment with no volumes:

```bash
docker compose down && docker compose up --build
```
