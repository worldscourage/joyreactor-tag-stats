"""A small, polite GraphQL client for joyreactor.cc."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from . import config

logger = logging.getLogger(__name__)


class JoyreactorError(RuntimeError):
    """Anything that stops us from getting usable data out of the API."""


class GraphQLClient:
    """Posts GraphQL queries, retries transient failures, throttles itself.

    The site's own frontend uses this endpoint, so we send the headers it
    expects from a browser and stay well below any sensible rate limit.
    """

    def __init__(
        self,
        endpoint: str = config.GRAPHQL_URL,
        *,
        timeout: float = config.REQUEST_TIMEOUT_SECONDS,
        delay: float = config.REQUEST_DELAY_SECONDS,
        max_retries: int = config.MAX_RETRIES,
        session: requests.Session | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self.delay = delay
        self.max_retries = max_retries
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": config.USER_AGENT,
                "Origin": config.SITE_URL,
                "Referer": f"{config.SITE_URL}/",
            }
        )
        self._last_request_at = 0.0
        self.requests_made = 0
        """Every attempt this client has sent, so callers can budget against it."""

    def execute(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Run one query and return its ``data`` payload."""
        payload = {"query": query, "variables": variables}
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            self._wait_turn()
            self.requests_made += 1
            try:
                response = self._session.post(
                    self.endpoint, json=payload, timeout=self.timeout
                )
                if response.status_code >= 500 or response.status_code == 429:
                    raise JoyreactorError(
                        f"HTTP {response.status_code} from {self.endpoint}"
                    )
                response.raise_for_status()
                body = response.json()
            except (requests.RequestException, ValueError, JoyreactorError) as error:
                last_error = error
                if attempt == self.max_retries:
                    break
                pause = config.RETRY_BACKOFF_SECONDS * attempt
                logger.warning(
                    "Request failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt,
                    self.max_retries,
                    error,
                    pause,
                )
                time.sleep(pause)
                continue

            if body.get("errors"):
                # GraphQL errors are the server telling us the query is wrong;
                # retrying an identical query would not help.
                messages = "; ".join(
                    str(item.get("message", item)) for item in body["errors"]
                )
                raise JoyreactorError(f"GraphQL error: {messages}")

            data = body.get("data")
            if data is None:
                raise JoyreactorError("GraphQL response contained no data")
            return data

        raise JoyreactorError(
            f"Giving up after {self.max_retries} attempts: {last_error}"
        ) from last_error

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> GraphQLClient:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def _wait_turn(self) -> None:
        """Keep at least ``delay`` seconds between two outgoing requests."""
        if not self.delay:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_at = time.monotonic()
