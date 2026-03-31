import re
from typing import Optional, Tuple
from bs4 import BeautifulSoup

SOFT_404_PATTERNS = [
    r"\bpage not found\b",
    r"\b404\b",
    r"\bnot found\b",
    r"\bdoesn't exist\b",
    r"\bno longer available\b",
]

FINGERPRINT_PATTERNS = [
    r"\b404\b",
    r"\bpage not found\b",
    r"\bnot found\b",
    r"\baccess denied\b",
    r"\bpermission denied\b",
]

def is_soft_404(text: str) -> bool:
    t = (text or "").lower()
    return any(re.search(pat, t) for pat in SOFT_404_PATTERNS)

def looks_like_login(final_url: str, html_text: Optional[str] = None) -> bool:
    u = (final_url or "").lower()
    if any(h in u for h in ("login", "signin", "sign-in", "auth")):
        return True

    t = (html_text or "").lower()
    if ("type=\"password\"" in t) or ("name=\"password\"" in t):
        return True
    if ("sign in" in t) or ("log in" in t) or ("login" in t and "password" in t):
        return True
    return False

def extract_title_h1(html_text: str) -> Tuple[str, str]:
    soup = BeautifulSoup(html_text, "html.parser")
    title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    h1 = (soup.find("h1").get_text(strip=True) if soup.find("h1") else "")
    return title.lower(), h1.lower()

def fingerprint_says_error(html_text: str) -> bool:
    t = (html_text or "").lower()
    if any(re.search(p, t) for p in FINGERPRINT_PATTERNS):
        return True

    title, h1 = extract_title_h1(html_text)
    if any(k in title for k in ("404", "not found", "error", "access denied")):
        return True
    if any(k in h1 for k in ("404", "not found", "error", "access denied")):
        return True

    return False

def normalize_http_bucket(status: int, final_url: str = "", html_text: Optional[str] = None) -> str:
    if 200 <= status < 400:
        if looks_like_login(final_url, html_text):
            return "auth_required"
        return "ok"

    if status == 401:
        return "auth_required"
    if status == 403:
        return "forbidden_or_blocked"
    if status == 404:
        return "not_found"
    if status == 410:
        return "gone"
    if status == 429:
        return "rate_limited"

    if 400 <= status < 500:
        return "client_error"
    if 500 <= status < 600:
        return "server_error"

    return f"http_{status}"
