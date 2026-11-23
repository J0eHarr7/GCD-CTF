# GCDSTExGLORY CTF By J0eHarr7

A collection of Dockerized web security challenges created for the GCDSTExGLORY CTF. Each challenge is self-contained and includes its own setup instructions, infrastructure, and organizer writeup where available.

**Flag format:** `GCDxGLORY{...}`  
**Category:** Web security, API security, HTTP, authentication, SSRF, and application business logic

> These environments contain intentional vulnerabilities. Run them only in an isolated lab or private CTF network.

---

## Challenges

| Challenge | Difficulty | Type | Host port | Directory |
|---|---|---|---:|---|
| Easy Web Pack | Easy | HTTP controls, JWT, broken access control | 5001–5003 | [`ctf-web-easy/`](ctf-web-easy/) |
| Lina's Blog | Medium–Hard | Integer overflow and broken entitlements | 8000 | [`lina_blog/linas-blog/`](lina_blog/linas-blog/) |
| LOTR | Expert | BOLA, stored injection, SSRF, confused-deputy chain | 7000 | [`onewiki/`](onewiki/) |
| The Ledger | Medium | Active-org boundary bypass, state-machine flaws, stale decisions | 8000 | [`the-ledger/`](the-ledger/) |
| TopCookiz | Medium | SQLi, UNION queries, admin escalation | 5000 | [`topcookizV3/`](topcookizV3/) |

### Easy Web Pack

The pack contains three independently hosted challenges:

1. **SecureVault** — HTTP method, proxy header, and user-agent validation
2. **TokenCorp** — weak JWT signing secret and token forgery
3. **NoteKeeper** — broken object-level authorization and IDOR

Full descriptions and organizer solutions are in [`ctf-web-easy/README.md`](ctf-web-easy/README.md).

---

## Quick start

Run an individual challenge from its directory:

```bash
cd the-ledger
docker compose up --build -d
```

Stop it when finished:

```bash
docker compose down
```

Before publishing an event, replace demo secrets and flag values in the challenge's `docker-compose.yml` or `compose.yaml`. Default ports are documented in the table above; confirm the port mapping in the challenge compose file because a few services use the same host port on separate networks.

### Docker Compose compatibility

Some older challenge folders use `docker-compose.yml`, while newer folders use `compose.yaml`. Docker Compose v2 accepts both names:

```bash
docker compose up --build -d
```

When using legacy Compose tooling, substitute:

```bash
docker-compose up --build -d
```

---

## Challenge writeups

| Challenge | Player-facing README | Organizer writeup |
|---|---|---|
| Easy Web Pack | [`ctf-web-easy/README.md`](ctf-web-easy/README.md) | Included in the challenge README |
| Lina's Blog | [`lina_blog/linas-blog/README.md`](lina_blog/linas-blog/README.md) | [`WRITEUP_SOLUTION.md`](lina_blog/linas-blog/WRITEUP_SOLUTION.md) |
| One Wiki | [`onewiki/README.md`](onewiki/README.md) | Included in the challenge README |
| The Ledger | [`the-ledger/README.md`](the-ledger/README.md) | [`the-ledger/WRITEUP.md`](the-ledger/WRITEUP.md) |
| TopCookiz | [`topcookizV3/README.md`](topcookizV3/README.md) | [`topcookizV3/WRITEUP.md`](topcookizV3/WRITEUP.md) |


---

## Repository layout

```text
GCD-CTF/
├── ctf-web-easy/       Three introductory web challenges
├── lina_blog/          Original Lina's Blog challenge
├── onewiki/            Multi-service SSRF exploit chain
├── the-ledger/         Pure JSON API state-machine challenge
└── topcookizV3/        Cookie and SQL-based web challenge
```

Each challenge generally contains:

- Docker and Compose configuration
- The challenge application and supporting services
- Seed data or player-facing accounts
- A README with setup and objectives
- A reference solver and/or organizer writeup
- Tests or verification scripts where applicable

---

## Event setup checklist

1. Review every flag and secret before the event.
2. Replace demo `SECRET_KEY`, `JWT_SECRET`, `ADMIN_KEY`, database credentials, and signing secrets.
3. Allocate unique host ports or run each challenge on a separate server/VM.
4. Isolate deliberately vulnerable containers from production networks.
5. Rebuild and reset the environment before distributing it to teams.
6. Verify that only intended ports are reachable.
7. Keep one copy of the solve scripts and writeups for organizers.

```bash
docker compose down -v --remove-orphans
docker compose up --build -d
```

Use `-v` only if the challenge has volumes or persistent state that should be cleared.

---

## License

No explicit license is currently defined. Add a license before reusing or redistributing the repository or challenge content publicly.
