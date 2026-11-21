# TopCookiz (Web — CTF challenge)

Stock-management app for a cookie factory. Break the auth, climb to admin.

## Run it

```bash
docker compose up --build
```

App will be at http://localhost:5000

Change the flag by editing `FLAG` in `docker-compose.yml` (and/or
`Dockerfile`) before building for a real competition — don't ship the
demo flag.

## Files

- `app.py` — Flask app (intentionally vulnerable, see comments marked `VULN #1` / `VULN #2`)
- `templates/` — HTML views
- `Dockerfile`, `docker-compose.yml` — containerization
- `solve.py` — reference solver, run with `python3 solve.py http://localhost:5000`
- `WRITEUP.md` — full writeup / walkthrough

## Seeded accounts

| username   | role     | notes                              |
|------------|----------|-------------------------------------|
| admin      | admin    | not meant to be reachable directly |
| J0eHarr7   | employee | target of the SQLi leak             |
| stock_bot  | employee | red herring                         |

Players are expected to discover J0eHarr7's password via the cookie
SQLi — it is not given out.
