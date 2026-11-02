"""PlantPulse product website: serves site/public and receives "Request a demo" submissions.

Standard library only (runs in the plain python image, nothing to install). Each request is appended to
$SITE_DATA_DIR/demo-requests.jsonl first, then e-mailed to $CONTACT_TO if SMTP is configured, so a request is never
lost when mail fails. Behind Caddy, which sets X-Forwarded-For.

Environment: CONTACT_TO, SITE_SMTP_HOST, SITE_SMTP_PORT (587), SITE_SMTP_USER, SITE_SMTP_PASSWORD, SITE_SMTP_FROM,
SITE_DATA_DIR (/data), SITE_PORT (8080).
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import smtplib
import ssl
import sys
import threading
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "public"
DATA_DIR = Path(os.environ.get("SITE_DATA_DIR", "/data"))
PORT = int(os.environ.get("SITE_PORT", "8080"))
MAX_BODY = 16 * 1024
RATE_LIMIT = 5  # submissions per IP per hour
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FIELDS = {  # name: (max length, required)
    "name": (120, True),
    "company": (160, True),
    "email": (160, True),
    "phone": (40, False),
    "industry": (40, False),
    "team_size": (20, False),
    "message": (3000, False),
    "lang": (5, False),
}
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/svg+xml", ".svg")

_hits: dict[str, list[float]] = {}
_lock = threading.Lock()


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}", file=sys.stderr, flush=True)


def rate_limited(ip: str) -> bool:
    now = time.time()
    with _lock:
        recent = [t for t in _hits.get(ip, []) if now - t < 3600]
        if len(recent) >= RATE_LIMIT:
            _hits[ip] = recent
            return True
        recent.append(now)
        _hits[ip] = recent
        if len(_hits) > 10000:  # keep memory bounded
            for k in list(_hits)[:5000]:
                _hits.pop(k, None)
        return False


def clean(data: dict) -> dict | None:
    out = {}
    for key, (limit, required) in FIELDS.items():
        val = data.get(key, "")
        val = val.strip() if isinstance(val, str) else ""
        if key != "message":
            val = " ".join(val.split())  # no line breaks in single-line fields (also blocks header injection)
        val = val[:limit]
        if required and not val:
            return None
        out[key] = val
    if not EMAIL_RE.match(out["email"]):
        return None
    return out


def send_mail(req: dict) -> bool:
    host, to = os.environ.get("SITE_SMTP_HOST", ""), os.environ.get("CONTACT_TO", "")
    if not host or not to:
        log("demo request saved; e-mail not sent (SITE_SMTP_HOST or CONTACT_TO not set)")
        return False
    sender = os.environ.get("SITE_SMTP_FROM") or os.environ.get("SITE_SMTP_USER") or to
    msg = EmailMessage()
    msg["Subject"] = f"PlantPulse demo request: {req['company']} ({req['name']})"
    msg["From"] = formataddr(("PlantPulse website", sender))
    msg["To"] = to
    msg["Reply-To"] = formataddr((req["name"], req["email"]))
    msg["Message-ID"] = make_msgid(domain="plantpulse-cmms.com")
    lines = [
        "New demo request from the PlantPulse website",
        "",
        f"Name:       {req['name']}",
        f"Company:    {req['company']}",
        f"E-mail:     {req['email']}",
        f"Phone:      {req['phone'] or '-'}",
        f"Industry:   {req['industry'] or '-'}",
        f"Team size:  {req['team_size'] or '-'}",
        f"Language:   {req['lang'] or '-'}",
        f"Received:   {req['received_at']}",
        "",
        "Message:",
        req["message"] or "-",
        "",
        "Reply to this e-mail to answer the requester directly.",
    ]
    msg.set_content("\n".join(lines))
    port = int(os.environ.get("SITE_SMTP_PORT", "587") or 587)
    try:
        ctx = ssl.create_default_context()
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            server.starttls(context=ctx)
        with server:
            user = os.environ.get("SITE_SMTP_USER", "")
            if user:
                server.login(user, os.environ.get("SITE_SMTP_PASSWORD", ""))
            server.send_message(msg)
        log(f"demo request e-mailed to {to}")
        return True
    except Exception as exc:  # the request is already saved; report and carry on
        log(f"demo request saved; e-mail FAILED: {exc!r}")
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "PlantPulseSite"
    sys_version = ""

    def log_message(self, fmt, *args):  # one compact line per request
        log(f"{self.client_ip()} {fmt % args}")

    def client_ip(self) -> str:
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() if fwd else self.client_address[0]

    def send(self, code: int, body: bytes, ctype: str, extra: dict | None = None, head: bool = False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def json(self, code: int, obj: dict):
        self.send(code, json.dumps(obj).encode(), "application/json", {"Cache-Control": "no-store"})

    def do_HEAD(self):
        self.do_GET(head=True)

    def do_GET(self, head: bool = False):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path == "/healthz":
            return self.send(200, b"ok", "text/plain", head=head)
        if path in ("", "/"):
            path = "/index.html"
        target = (ROOT / path.lstrip("/")).resolve()
        if ROOT not in target.parents or not target.is_file():
            return self.send(302, b"", "text/plain", {"Location": "/"}, head=head)
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        cache = "no-cache" if target.suffix == ".html" else "public, max-age=86400"
        self.send(200, target.read_bytes(), ctype, {"Cache-Control": cache}, head=head)

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/demo-request":
            return self.json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            return self.json(400, {"error": "bad request"})
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError
        except Exception:
            return self.json(400, {"error": "bad request"})
        if str(data.get("website", "")).strip():  # honeypot field humans never see
            log(f"{self.client_ip()} demo request dropped (honeypot)")
            return self.json(200, {"ok": True})
        ip = self.client_ip()
        if rate_limited(ip):
            return self.json(429, {"error": "too many requests"})
        req = clean(data)
        if req is None:
            return self.json(400, {"error": "name, company and a valid e-mail are required"})
        req["received_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        req["ip"] = ip
        req["user_agent"] = (self.headers.get("User-Agent", "") or "")[:200]
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with _lock, open(DATA_DIR / "demo-requests.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(req, ensure_ascii=False) + "\n")
        except OSError as exc:
            log(f"could not save demo request: {exc!r}")
            return self.json(500, {"error": "could not save"})
        log(f"demo request from {req['company']!r} <{req['email']}>")
        threading.Thread(target=send_mail, args=(req,), daemon=True).start()
        return self.json(200, {"ok": True})


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "test-mail":
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        ok = send_mail({"name": "Test", "company": "PlantPulse test e-mail", "email": "test@example.com", "phone": "",
                        "industry": "", "team_size": "", "message": "If you can read this, the website can send"
                        " demo requests by e-mail.", "lang": "en", "received_at": now})
        sys.exit(0 if ok else 1)
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    log(f"PlantPulse site on :{PORT}, mail to {os.environ.get('CONTACT_TO') or '(not set)'}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
