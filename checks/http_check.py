from __future__ import annotations

from typing import Dict, Optional, Tuple, Any
import requests

from bookmark_checker.checks.classify import (
    normalize_http_bucket,
    is_soft_404,
    fingerprint_says_error,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

def build_headers() -> Dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }


def check_url_once(
    *,
    session: requests.Session,
    url: str,
    timeout: Tuple[int, int],
    enable_soft_404: bool,
    enable_fingerprinting: bool,
) -> Dict[str, Any]:
    """
    One attempt only. No retries here.
    Returns a dict shaped like your existing result.
    """
    headers = build_headers()

    result: Dict[str, Any] = {
        "input_url": url,
        "final_url": "",
        "status_code": "",
        "ok": False,
        "error_type": "",
        "notes": "",
        # Optional: keep these if you later want Retry-After support
        # "retry_after_header": "",
    }

    try:
        resp = session.head(url, headers=headers, allow_redirects=True, timeout=timeout)
        status = resp.status_code

        # If HEAD is blocked/meaningless, fall back to GET.
        if status in (403, 405) or (status >= 400 and status != 404):
            resp = session.get(url, headers=headers, allow_redirects=True, timeout=timeout)
            status = resp.status_code

        result["final_url"] = resp.url
        result["status_code"] = status

        content_type = (resp.headers.get("Content-Type") or "").lower()
        html_text: Optional[str] = None

        # Only capture body when method is GET
        if "text/html" in content_type and resp.request.method != "HEAD":
            html_text = resp.text

        bucket = normalize_http_bucket(status, result["final_url"], html_text)

        # Fingerprinting overlay
        if enable_fingerprinting and html_text and fingerprint_says_error(html_text):
            result["error_type"] = "content_error_page"
            result["notes"] = "200-399 but content fingerprint looks like an error page."
            return result

        if bucket == "ok":
            if enable_soft_404 and "text/html" in content_type:
                if resp.request.method == "HEAD":
                    resp2 = session.get(resp.url, headers=headers, allow_redirects=True, timeout=timeout)
                    if is_soft_404(resp2.text):
                        result["error_type"] = "soft_404"
                        result["notes"] = "200-399 but content looks like not-found."
                    else:
                        result["ok"] = True
                else:
                    if is_soft_404(resp.text):
                        result["error_type"] = "soft_404"
                        result["notes"] = "200-399 but content looks like not-found."
                    else:
                        result["ok"] = True
            else:
                result["ok"] = True
        else:
            result["error_type"] = bucket

    except requests.exceptions.TooManyRedirects:
        result["error_type"] = "too_many_redirects"
    except requests.exceptions.InvalidURL:
        result["error_type"] = "invalid_url"
    except requests.exceptions.SSLError:
        result["error_type"] = "tls_error"
    except requests.exceptions.ConnectTimeout:
        result["error_type"] = "connect_timeout"
    except requests.exceptions.ReadTimeout:
        result["error_type"] = "read_timeout"
    except requests.exceptions.ConnectionError as e:
        msg = str(e).lower()
        if "name or service not known" in msg or "getaddrinfo failed" in msg or "nodename nor servname" in msg:
            result["error_type"] = "dns_failure"
        else:
            result["error_type"] = "connection_error"
        result["notes"] = str(e)
    except Exception as e:
        result["error_type"] = "exception"
        result["notes"] = str(e)

    return result
