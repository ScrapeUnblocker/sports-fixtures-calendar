"""A small client for the ScrapeUnblocker SofaScore endpoints this tool uses.

Docs: https://docs.scrapeunblocker.com/plugins/sofascore
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import requests

API_URL = "https://api.scrapeunblocker.com"
# Errors worth another try: rate limit and upstream hiccups. A 400 or 404 is
# an answer about the input and is never retried.
RETRY_STATUSES = {429, 500, 502, 503, 504}


class ApiError(Exception):
    """The API refused the call (bad input, no such entity, or out of retries)."""

    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message


def api_key_from_env() -> Optional[str]:
    return os.environ.get("SCRAPEUNBLOCKER_API_KEY") or os.environ.get("SCRAPEUNBLOCKER_KEY")


class SofaScore:
    def __init__(self, api_key: Optional[str] = None, *, timeout: float = 120,
                 retries: int = 3, base_url: str = API_URL,
                 session: Optional[requests.Session] = None):
        self.api_key = api_key or api_key_from_env()
        if not self.api_key:
            raise ApiError(401, "No API key: set SCRAPEUNBLOCKER_API_KEY "
                                "(get one at https://scrapeunblocker.com).")
        self.timeout = timeout
        self.retries = retries
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.calls = 0

    def _post(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        params = {k: v for k, v in params.items() if v not in (None, "")}
        last: Optional[ApiError] = None
        for attempt in range(self.retries):
            self.calls += 1
            try:
                resp = self.session.post(self.base_url + path, params=params,
                                         headers={"x-scrapeunblocker-key": self.api_key},
                                         timeout=self.timeout)
            except requests.RequestException as exc:
                last = ApiError(0, str(exc))
            else:
                if resp.status_code == 200:
                    return resp.json()
                last = ApiError(resp.status_code, resp.text.strip()[:300])
                if resp.status_code not in RETRY_STATUSES:
                    raise last
            time.sleep(2 * (attempt + 1))
        raise last or ApiError(0, "no answer")

    def team(self, team: str, *, sport: Optional[str] = None,
             include: str = "last_matches,next_matches") -> Dict[str, Any]:
        """A team (or a tennis player, MMA fighter and other individual
        competitors) by id, sofascore.com link or name."""
        return self._post("/sports/sofascore-team",
                          {"team": team, "sport": sport, "include": include})

    def tournament(self, tournament: str, *, sport: Optional[str] = None,
                   include: str = "last_matches,next_matches") -> Dict[str, Any]:
        """A competition by id, sofascore.com link or name, current season."""
        return self._post("/sports/sofascore-tournament",
                          {"tournament": tournament, "sport": sport, "include": include})
