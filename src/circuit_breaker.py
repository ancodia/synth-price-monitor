"""
Circuit breaker pattern to prevent cascade failures when sites are down.

After failure_threshold consecutive failures for a site, the circuit opens
and all requests to that site are skipped for `timeout` duration.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict
from loguru import logger


class CircuitBreaker:
    """
    Circuit breaker to prevent repeated scraping of failing sites.

    States:
        CLOSED  - Normal operation, requests pass through
        OPEN    - Site failing, requests are skipped for `timeout`
    """

    def __init__(
        self, failure_threshold: int = 3, timeout: timedelta = timedelta(hours=1)
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures: Dict[str, int] = defaultdict(int)
        self.opened_at: Dict[str, datetime] = {}

    def is_open(self, site: str) -> bool:
        """Return True if the circuit is open (site should be skipped)."""
        if site not in self.opened_at:
            return False

        if datetime.now() - self.opened_at[site] > self.timeout:
            logger.info(f"Circuit breaker timeout elapsed for {site}, resetting")
            self.reset(site)
            return False

        return True

    def record_success(self, site: str) -> None:
        """Record a successful scrape and clear any failure state."""
        if site in self.failures:
            logger.info(f"Circuit breaker: clearing failures for {site}")
            self.reset(site)

    def record_failure(self, site: str) -> None:
        """Record a failed scrape and open the circuit if threshold reached."""
        self.failures[site] += 1

        if self.failures[site] >= self.failure_threshold:
            self.opened_at[site] = datetime.now()
            logger.warning(
                f"Circuit breaker OPENED for {site} after {self.failures[site]} failures. "
                f"Will retry after {self.timeout.total_seconds() / 3600:.1f}h"
            )

    def reset(self, site: str) -> None:
        """Reset the circuit breaker for a site."""
        self.failures.pop(site, None)
        self.opened_at.pop(site, None)
