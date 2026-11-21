import os
from flask import Flask, request, jsonify

app = Flask(__name__)
FLAG = os.environ.get("FLAG", "CTF{m3th0ds_4nd_h34d3rs_4r3_us3r_c0ntr0ll3d}")

INDEX = """<!doctype html>
<html><head><title>SecureVault</title>
<style>body{font-family:monospace;background:#0d1117;color:#c9d1d9;max-width:640px;margin:60px auto}
code{background:#161b22;padding:2px 6px;border-radius:4px}</style></head>
<body>
<h1>🔐 SecureVault</h1>
<p>Our vault is only reachable by internal staff using the official client.</p>
<p>Endpoint: <code>/vault</code></p>
<p>Try it. The server will tell you what is wrong.</p>
<!-- dev note: browsers only send GET and POST. Real clients can do more. -->
</body></html>"""


@app.route("/")
def index():
    return INDEX


@app.route("/vault", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def vault():
    # Stage 1: HTTP method
    if request.method != "PUT":
        return jsonify(
            error=f"Method {request.method} not allowed.",
            hint="The vault only accepts requests that REPLACE a resource.",
        ), 405

    # Stage 2: trusted origin (naively trusts a client-controlled header)
    xff = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if xff != "127.0.0.1":
        return jsonify(
            error="Access denied: vault is only reachable from localhost.",
            hint="Who does the server think you are? Proxies add a header for that.",
        ), 403

    # Stage 3: official client
    if request.headers.get("User-Agent") != "VaultClient/1.0":
        return jsonify(
            error="Unknown client.",
            hint="Only VaultClient/1.0 may connect.",
        ), 403

    # Stage 4: custom role header
    if request.headers.get("X-Vault-Role", "").lower() != "admin":
        return jsonify(
            error="Insufficient privileges.",
            hint="Set a custom header X-Vault-Role to the highest role.",
        ), 403

    return jsonify(message="Vault unlocked!", flag=FLAG)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
