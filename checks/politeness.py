from collections import defaultdict
from threading import Lock
from typing import Dict
import time


# One lock per domain shared across threads
_domain_locks: Dict[str, Lock] = defaultdict(Lock)
_domain_last_hit: Dict[str, float] = defaultdict(float)


def polite_wait_domain(domain: str, delay_sec: float) -> None:
    """
    Enforce per-domain politeness delay across threads.
    """
    if delay_sec <= 0:
        return

    lock = _domain_locks[domain]
    with lock:
        now = time.time()
        elapsed = now - _domain_last_hit[domain]
        if elapsed < delay_sec:
            time.sleep(delay_sec - elapsed)
        _domain_last_hit[domain] = time.time()
