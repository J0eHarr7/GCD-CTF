# LINA'S BLOG — CTF Web Challenge

**Category:** Web / Business Logic
**Difficulty:** Medium–Hard
**Flags:** 1

## Story

Lina is a cybersecurity writer who publishes free technical articles and
gates her deepest research behind a premium paywall. Somewhere in her
checkout flow, something doesn't add up.

## Goal

Retrieve the single flag hidden behind **Lina's Private Security Research**
— an article priced well beyond what any starting account can legitimately
afford.

## Running it

```bash
docker compose up --build
```

The app is served on `http://localhost:8000`.

A fresh random flag is generated on every container start unless you set
the `FLAG` environment variable in `compose.yaml` (useful for scored,
reproducible deployments).

## Rules of engagement

- Everything you need is reachable from the running application. There is
  no out-of-band information required.
- Only one flag exists, and it is only ever returned from the fully
  unlocked `/premium/lina-private-research` page.
- Guessing URLs, tampering with displayed statuses in the browser, or
  directly hitting `/premium/<slug>` without going through a real purchase
  will not work.

## Project layout

```
linas-blog/
├── app/
│   ├── auth/          # register/login
│   ├── articles/      # public feed, free articles, premium previews
│   ├── checkout/      # quote + confirm API (the vulnerable flow)
│   ├── billing/
│   │   └── legacy_arithmetic.py   # fixed-width accumulator
│   ├── entitlements/  # library + access-granting logic
│   ├── challenge/
│   │   └── final_flag.py          # flag generation/storage
│   ├── templates/
│   └── static/
├── seed/articles.json
├── tests/             # also doubles as an automated solver (see tests/test_full_exploit_chain.py)
├── Dockerfile
├── compose.yaml
└── requirements.txt
```

Happy hunting.
