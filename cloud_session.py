"""Anonymous pilot sessions. Signatures and the API key never enter the HTML."""
from __future__ import annotations
import hashlib
import hmac
import os
import re
import secrets
import time
from urllib.parse import urlsplit

COOKIE = "qc_browser_session"
TTL = 24 * 60 * 60


def secret():
    value = os.environ.get("QC_API_KEY", "")
    if not value:
        raise RuntimeError("Set QC_API_KEY on the server to sign browser sessions.")
    return value.encode("utf-8")


def signature(payload):
    return hmac.new(secret(), ("qc-browser-v1:" + payload).encode("ascii"), hashlib.sha256).hexdigest()


def session_id(token):
    if not isinstance(token, str) or len(token) > 160:
        return None
    parts = token.split(".")
    if len(parts) != 3 or not re.fullmatch(r"[a-f0-9]{64}", parts[0]) or not re.fullmatch(r"[0-9]{10}", parts[1]) or not re.fullmatch(r"[a-f0-9]{64}", parts[2]):
        return None
    payload = ".".join(parts[:2])
    if int(parts[1]) < time.time() or not hmac.compare_digest(signature(payload), parts[2]):
        return None
    return parts[0]


def owner_id(session):
    return "browser:" + hashlib.sha256(session.encode("ascii")).hexdigest()


def browser_origin(request):
    # Render terminates TLS in front of Uvicorn; its external URL supplies the
    # HTTPS origin reliably. Custom domains use the host seen by the app.
    external = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    if external and urlsplit(external).netloc == request.url.netloc:
        return external
    scheme = "https" if os.environ.get("RENDER") == "true" else request.url.scheme
    return scheme + "://" + request.url.netloc


def issue_cookie(response, request):
    token = request.cookies.get(COOKIE, "")
    sid = session_id(token)
    if sid is None:
        sid = secrets.token_hex(32)
    # Refresh the expiry on a normal page reload, retaining the browser owner.
    payload = sid + "." + str(int(time.time()) + TTL)
    token = payload + "." + signature(payload)
    response.set_cookie(COOKIE, token, max_age=TTL, httponly=True,
                        secure=browser_origin(request).startswith("https://"),
                        samesite="strict", path="/")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
