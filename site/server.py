"""PlantPulse product website: serves site/public and receives "Request a demo" submissions.

Standard library only (runs in the plain python image, nothing to install). Each request is appended to
$SITE_DATA_DIR/demo-requests.jsonl first, then e-mailed to $CONTACT_TO if SMTP is configured, so a request is never
lost when mail fails. Behind Caddy, which sets X-Forwarded-For.

Environment: CONTACT_TO, SITE_SMTP_HOST, SITE_SMTP_PORT (587), SITE_SMTP_USER, SITE_SMTP_PASSWORD, SITE_SMTP_FROM,
SITE_DATA_DIR (/data), SITE_PORT (8080), and from scripts/demo.sh DEMO_URL, DEMO_PASSWORD: POST /api/demo-access
e-mails the visitor the demo sign-in details at once and tells CONTACT_TO who took the demo.
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


def smtp_send(msg: EmailMessage) -> None:
    """Send one message with the website's own mail server (SITE_SMTP_*); raises on failure."""
    host = os.environ.get("SITE_SMTP_HOST", "")
    port = int(os.environ.get("SITE_SMTP_PORT", "587") or 587)
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


def sender_address() -> str:
    return os.environ.get("SITE_SMTP_FROM") or os.environ.get("SITE_SMTP_USER") or os.environ.get("CONTACT_TO", "")


def send_mail(req: dict) -> bool:
    """Tell the PlantPulse team about a submission (demo request, or someone who took the demo)."""
    host, to = os.environ.get("SITE_SMTP_HOST", ""), os.environ.get("CONTACT_TO", "")
    if not host or not to:
        log("submission saved; e-mail not sent (SITE_SMTP_HOST or CONTACT_TO not set)")
        return False
    access = req.get("kind") == "demo-access"
    msg = EmailMessage()
    what = "demo access" if access else "demo request"
    # The owner tells the two kinds apart at a glance in the inbox (Arabic first, the owner's language).
    if access:
        msg["Subject"] = f"🟢 جرّب الـ Demo – Demo access: {req['company']} ({req['name']})"
    else:
        msg["Subject"] = f"📞 طلب تواصل – Contact request: {req['company']} ({req['name']})"
    msg["From"] = formataddr(("PlantPulse website", sender_address()))
    msg["To"] = to
    msg["Reply-To"] = formataddr((req["name"], req["email"]))
    msg["Message-ID"] = make_msgid(domain="plantpulse-cmms.com")
    lines = [
        "🟢 Try the demo: this visitor already received the demo sign-in by e-mail. Nothing to do; follow up in 1-2 days."
        if access else "📞 Contact us: this visitor wants to talk. Reply to this e-mail or call within one working day.",
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
        "Reply to this e-mail to answer them directly.",
    ]
    msg.set_content("\n".join(lines))
    try:
        smtp_send(msg)
        log(f"{what} e-mailed to {to}")
        return True
    except Exception as exc:  # the submission is already saved; report and carry on
        log(f"{what} saved; e-mail FAILED: {exc!r}")
        return False


DEMO_ACCOUNTS = [  # the same password for all; scripts/demo.sh keeps it from being changed
    ("Maintenance manager", "مدير الصيانة", "manager@demo.example.com"),
    ("Planner", "مخطط الصيانة", "planner@demo.example.com"),
    ("Technician (best on a phone)", "فني (الأفضل على الجوال)", "tech1@demo.example.com"),
]


def demo_available() -> bool:
    return all(os.environ.get(k) for k in ("DEMO_URL", "DEMO_PASSWORD", "SITE_SMTP_HOST"))


def _demo_lines(ar: bool) -> list[str]:
    """The demo address and accounts, for the visitor's e-mail (empty when the demo is not running)."""
    url, pw = os.environ.get("DEMO_URL", ""), os.environ.get("DEMO_PASSWORD", "")
    if not (url and pw):
        return []
    if ar:
        return [
            f"  العنوان:      {url}",
            f"  كلمة المرور:  {pw}   (نفسها لكل الحسابات التالية)",
            "",
            *[f"  {role}:  {email}" for _, role, email in DEMO_ACCOUNTS],
            "",
            "ادخل بحساب مدير الصيانة لترى كل شيء، وبحساب الفني لترى تطبيق الموقع على جوالك.",
            "البيانات تجريبية ومشتركة بين كل الزوار، وتعود لحالتها الأصلية كل ليلة.",
        ]
    return [
        f"  Address:   {url}",
        f"  Password:  {pw}   (the same for every account below)",
        "",
        *[f"  {role}:  {email}" for role, _, email in DEMO_ACCOUNTS],
        "",
        "Sign in as the manager to see everything, as the technician to see the shop-floor app on your phone.",
        "The demo uses SAMPLE data shared by all visitors, and goes back to the original data every night.",
    ]


def _send_to_visitor(req: dict, subject: str, body: list[str]) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("PlantPulse", sender_address()))
    msg["To"] = formataddr((req["name"], req["email"]))
    contact = os.environ.get("CONTACT_TO", "")
    if contact:
        msg["Reply-To"] = contact
    msg["Message-ID"] = make_msgid(domain="plantpulse-cmms.com")
    msg.set_content("\n".join(body))
    smtp_send(msg)


def send_demo_access(req: dict) -> None:
    """E-mail the visitor the demo address and accounts, in the language they used on the website. Raises on failure."""
    if req.get("lang") == "ar":
        body = [f"مرحباً {req['name']}،", "", "شكراً لاهتمامك بـ PlantPulse. هذه بيانات الدخول إلى النسخة التجريبية:", "",
                *_demo_lines(True), "", "تريد أن ترى النظام بأصول ومعدات مصنعك؟ فقط رد على هذا الإيميل.", "",
                "PlantPulse – إدارة الصيانة للمنشآت الصناعية"]
        _send_to_visitor(req, "بيانات الدخول إلى النسخة التجريبية من PlantPulse", body)
    else:
        body = [f"Hello {req['name']},", "", "Thank you for your interest in PlantPulse. Here is your access to the live demo:", "",
                *_demo_lines(False), "", "Want to see it with your own plant and assets? Just reply to this e-mail.", "",
                "PlantPulse – maintenance management for industrial plants"]
        _send_to_visitor(req, "Your PlantPulse demo access", body)


def send_ack(req: dict) -> None:
    """Tell someone who used the contact form that we have it; include the demo access so they can try it meanwhile."""
    if not os.environ.get("SITE_SMTP_HOST") or recipient_limited(req["email"]):
        return
    ar = req.get("lang") == "ar"
    demo = _demo_lines(ar)
    if ar:
        body = [f"مرحباً {req['name']}،", "", f"شكراً لتواصلك مع PlantPulse. استلمنا طلبك ({req['company']}) وسنتواصل معك خلال يوم عمل واحد.", ""]
        if demo:
            body += ["حتى ذلك الحين، يمكنك تجربة النظام بنفسك:", "", *demo, ""]
        body += ["لأي إضافة، فقط رد على هذا الإيميل.", "", "PlantPulse – إدارة الصيانة للمنشآت الصناعية"]
        subject = "استلمنا طلبك – PlantPulse"
    else:
        body = [f"Hello {req['name']},", "", f"Thank you for contacting PlantPulse. We have your request ({req['company']}) "
                "and will get back to you within one working day.", ""]
        if demo:
            body += ["Meanwhile, you can try the system yourself:", "", *demo, ""]
        body += ["Anything to add? Just reply to this e-mail.", "", "PlantPulse – maintenance management for industrial plants"]
        subject = "We have your request – PlantPulse"
    try:
        _send_to_visitor(req, subject, body)
        log(f"confirmation e-mailed to {req['email']}")
    except Exception as exc:
        log(f"confirmation to {req['email']} FAILED: {exc!r}")


_sent_to: dict[str, list[float]] = {}


def recipient_limited(email: str) -> bool:
    """At most 3 demo e-mails per address per day (the form must not become a way to flood someone's inbox)."""
    now, key = time.time(), email.lower()
    with _lock:
        recent = [t for t in _sent_to.get(key, []) if now - t < 86400]
        if len(recent) >= 3:
            _sent_to[key] = recent
            return True
        recent.append(now)
        _sent_to[key] = recent
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
        route = self.path.split("?", 1)[0]
        if route not in ("/api/demo-request", "/api/demo-access"):
            return self.json(404, {"error": "not found"})
        access = route == "/api/demo-access"
        if access and not demo_available():
            return self.json(503, {"error": "demo not available"})
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
        if access and recipient_limited(req["email"]):
            return self.json(429, {"error": "too many requests"})
        req["kind"] = "demo-access" if access else "demo-request"
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
        log(f"{req['kind']} from {req['company']!r} <{req['email']}>")
        if access:
            try:  # sent while the visitor waits, so the page can say whether it worked
                send_demo_access(req)
                log(f"demo access e-mailed to {req['email']}")
            except Exception as exc:
                log(f"demo access e-mail to {req['email']} FAILED: {exc!r}")
                return self.json(502, {"error": "could not send"})
        threading.Thread(target=send_mail, args=(req,), daemon=True).start()
        if not access:
            threading.Thread(target=send_ack, args=(req,), daemon=True).start()
        return self.json(200, {"ok": True})


def send_welcome(c: dict, preview: bool = False) -> None:
    """Welcome e-mail for a new customer's first administrator (scripts/customer.sh new / welcome). Raises on failure.
    c: name, email, company, url, password, lang ("ar" or "en")."""
    if c.get("lang") == "ar":
        subject = f"نظام PlantPulse الخاص بـ {c['company']} جاهز"
        body = [
            "مرحباً،",
            "",
            f"تم تجهيز نظام PlantPulse الخاص بـ {c['company']}. هذه بيانات الدخول كمسؤول النظام (Admin):",
            "",
            f"  العنوان:            {c['url']}",
            f"  البريد الإلكتروني:  {c['email']}",
            f"  كلمة المرور الأولى: {c['password']}",
            "",
            "الخطوات الأولى:",
            "  1. ادخل وغيّر كلمة المرور فوراً (قائمة الملف الشخصي ← تغيير كلمة المرور).",
            "  2. راجع الأقسام والمصنع من صفحة الإدارة (Admin).",
            "  3. أضف المستخدمين، أو استوردهم من قالب Excel.",
            "  4. استورد سجل الأصول وخطط الصيانة من قوالب Excel الموجودة في النظام.",
            "",
            "هذا النظام خاص بشركتكم: قاعدة بيانات ومرفقات مستقلة، مع نسخ احتياطي كل ليلة.",
            "لأي سؤال أو مساعدة في إدخال البيانات، فقط رد على هذا الإيميل.",
            "",
            "PlantPulse – إدارة الصيانة للمنشآت الصناعية",
        ]
    else:
        subject = f"Your PlantPulse for {c['company']} is ready"
        body = [
            "Hello,",
            "",
            f"PlantPulse for {c['company']} is ready. These are your administrator sign-in details:",
            "",
            f"  Address:         {c['url']}",
            f"  E-mail:          {c['email']}",
            f"  First password:  {c['password']}",
            "",
            "First steps:",
            "  1. Sign in and change the password straight away (profile menu > Change password).",
            "  2. Check the plant and departments in Admin.",
            "  3. Add your users, or import them from the Excel template.",
            "  4. Import your asset register and PM plans from the Excel templates in the system.",
            "",
            "This system is yours alone: its own database and attachments, backed up every night.",
            "Any question, or help loading your data? Just reply to this e-mail.",
            "",
            "PlantPulse – maintenance management for industrial plants",
        ]
    if preview:  # show exactly what would be sent, send nothing
        print(f"From:     PlantPulse <{sender_address()}>")
        print(f"To:       {c['email']}")
        print(f"Reply-To: {os.environ.get('CONTACT_TO', '')}")
        print(f"Subject:  {subject}")
        print("-" * 60)
        print("\n".join(body))
        print("-" * 60)
        return
    _send_to_visitor({"name": c["company"], "email": c["email"]}, subject, body)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "test-mail":
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        ok = send_mail({"name": "Test", "company": "PlantPulse test e-mail", "email": "test@example.com", "phone": "",
                        "industry": "", "team_size": "", "kind": "demo-request", "message": "If you can read this, the website can send"
                        " demo requests by e-mail.", "lang": "en", "received_at": now})
        sys.exit(0 if ok else 1)
    if len(sys.argv) > 1 and sys.argv[1] == "mail":  # JSON on stdin from scripts/customer.sh: reminders
        m = json.loads(sys.stdin.read())  # {to (empty = CONTACT_TO), to_name, subject, body: [lines], preview}
        to = m.get("to") or os.environ.get("CONTACT_TO", "")
        if m.get("preview"):
            print(f"From:     PlantPulse <{sender_address()}>\nTo:       {to}\nSubject:  {m['subject']}\n" + "-" * 60)
            print("\n".join(m["body"]) + "\n" + "-" * 60)
            sys.exit(0)
        if not os.environ.get("SITE_SMTP_HOST") or not to:
            print("No mail server (or no recipient) set for the website: e-mail not sent.")
            sys.exit(1)
        try:
            _send_to_visitor({"name": m.get("to_name") or "", "email": to}, m["subject"], m["body"])
        except Exception as exc:
            print(f"E-mail FAILED: {exc!r}")
            sys.exit(1)
        print(f"E-mail sent to {to}.")
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "welcome":  # JSON on stdin, from scripts/customer.sh
        c = json.loads(sys.stdin.read())
        if c.get("preview"):
            send_welcome(c, preview=True)
            sys.exit(0)
        if not os.environ.get("SITE_SMTP_HOST"):
            print("No mail server set for the website: welcome e-mail not sent.")
            sys.exit(1)
        try:
            send_welcome(c)
        except Exception as exc:
            print(f"Welcome e-mail FAILED: {exc!r}")
            sys.exit(1)
        print(f"Welcome e-mail sent to {c['email']}.")
        sys.exit(0)
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    log(f"PlantPulse site on :{PORT}, mail to {os.environ.get('CONTACT_TO') or '(not set)'}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
