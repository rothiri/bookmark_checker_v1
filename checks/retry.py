from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Union


@dataclass(frozen=True)
class RetryConfig:
    enabled: bool = True
    max_attempts: int = 3            # includes first attempt
    base_delay: float = 2.0          # seconds
    backoff_multiplier: float = 2.0
    jitter: float = 0.5              # +/- seconds
    respect_retry_after: bool = True
    max_delay: float = 60.0


DEFAULT_RETRYABLE_ERROR_TYPES = {
    "connect_timeout",
    "read_timeout",
    "dns_failure",
    "connection_error",
    "rate_limited",   # 429
    "server_error",   # 5xx
}

DEFAULT_NEVER_RETRY_ERROR_TYPES = {
    "ok",
    "not_found",
    "gone",
    "forbidden_or_blocked",
    "auth_required",
    "client_error",
    "tls_error",
    "soft_404",
    "exception",
    "invalid_url",
    "too_many_redirects",
}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def parse_retry_after_seconds(retry_after_value: Optional[str]) -> Optional[float]:
    if not retry_after_value:
        return None
    try:
        return float(int(retry_after_value.strip()))
    except Exception:
        return None


def compute_backoff_delay(
    attempt_index: int,
    cfg: RetryConfig,
    retry_after_seconds: Optional[float] = None,
) -> float:
    delay = cfg.base_delay * (cfg.backoff_multiplier ** (attempt_index - 1))

    if cfg.respect_retry_after and retry_after_seconds is not None:
        delay = max(delay, retry_after_seconds)

    if cfg.jitter > 0:
        delay += random.uniform(-cfg.jitter, cfg.jitter)

    return _clamp(delay, 0.0, cfg.max_delay)


def is_retryable_failure(
    *,
    ok: bool,
    error_type: Optional[str],
    status_code: Optional[int] = None,
    retryable_error_types=DEFAULT_RETRYABLE_ERROR_TYPES,
    never_retry_error_types=DEFAULT_NEVER_RETRY_ERROR_TYPES,
) -> bool:
    if ok:
        return False

    if error_type:
        if error_type in never_retry_error_types:
            return False
        if error_type in retryable_error_types:
            return True

    if status_code == 429:
        return True
    if status_code is not None and 500 <= status_code <= 599:
        return True

    return False


ResultLike = Union[Dict[str, Any], Any]
CheckOnceFn = Callable[..., ResultLike]
LoggerFn = Callable[[str], None]


def _get(result: ResultLike, key: str, default=None):
    if isinstance(result, dict):
        return result.get(key, default)
    return getattr(result, key, default)


def _set(result: ResultLike, key: str, value: Any) -> None:
    if isinstance(result, dict):
        result[key] = value
    else:
        setattr(result, key, value)


def _append_note(result: ResultLike, text: str) -> None:
    existing = _get(result, "notes", "")
    if existing:
        existing = existing.rstrip()
        new_notes = f"{existing} | {text}"
    else:
        new_notes = text
    _set(result, "notes", new_notes)


def check_url_with_retries(
    *,
    url: str,
    session: Any,
    check_once: CheckOnceFn,
    retry_cfg: RetryConfig,
    logger: Optional[LoggerFn] = None,
    check_once_kwargs: Optional[Dict[str, Any]] = None,
) -> ResultLike:
    if check_once_kwargs is None:
        check_once_kwargs = {}

    retry_history = []
    retry_count = 0
    retried = False

    if not retry_cfg.enabled or retry_cfg.max_attempts <= 1:
        result = check_once(url=url, session=session, **check_once_kwargs)
        _set(result, "retried", False)
        _set(result, "retry_count", 0)
        _set(result, "retry_history", "")
        return result

    last_result: Optional[ResultLike] = None

    for attempt_num in range(1, retry_cfg.max_attempts + 1):
        result = check_once(url=url, session=session, **check_once_kwargs)
        last_result = result

        ok = bool(_get(result, "ok", False))
        error_type = _get(result, "error_type", None)
        status_code = _get(result, "status_code", None)

        outcome_label = "ok" if ok else (str(error_type) if error_type else f"status_{status_code}")
        retry_history.append(outcome_label)

        if ok:
            break

        if not is_retryable_failure(ok=ok, error_type=error_type, status_code=status_code):
            break

        if attempt_num >= retry_cfg.max_attempts:
            break

        retry_after = None
        if status_code == 429:
            ra_val = _get(result, "retry_after_header", None) or _get(result, "retry_after", None)
            if isinstance(ra_val, (int, float)):
                retry_after = float(ra_val)
            elif isinstance(ra_val, str):
                retry_after = parse_retry_after_seconds(ra_val)

        delay = compute_backoff_delay(attempt_index=attempt_num, cfg=retry_cfg, retry_after_seconds=retry_after)

        retry_count += 1
        retried = True

        if logger:
            logger(f"[retry] {url} attempt {attempt_num}/{retry_cfg.max_attempts} failed ({outcome_label}); sleeping {delay:.2f}s")

        time.sleep(delay)

    if last_result is None:
        last_result = {"ok": False, "error_type": "exception", "notes": "No result produced"}

    _set(last_result, "retried", retried)
    _set(last_result, "retry_count", retry_count)
    _set(last_result, "retry_history", " → ".join(retry_history))

    if retried:
        _append_note(last_result, f"retried {retry_count}x ({_get(last_result, 'retry_history', '')})")

    return last_result
