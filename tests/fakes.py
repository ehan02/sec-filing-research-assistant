"""Offline EDGAR: a URL-routed fake HTTP client and a downloader wired to it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from src.filings.edgar import EdgarClient, EdgarDownloader

TEST_AGENT = "Test Runner test@example.com"


def response(url: str, status: int = 200, payload: object = None,
             content: bytes | None = None) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp.url = url
    resp._content = content if content is not None else json.dumps(payload).encode()
    return resp


class FakeEdgar:
    """Routes URLs to canned responses by suffix and records every request.

    A route's value is a JSON-able object, raw ``bytes``, or an ``int`` HTTP
    error status. Unrouted URLs raise a 404.
    """

    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url: str) -> requests.Response:
        self.calls.append(url)
        for suffix, payload in self.routes.items():
            if url.endswith(suffix):
                if isinstance(payload, int):
                    resp = response(url, status=payload, content=b"")
                    raise requests.HTTPError(response=resp)
                if isinstance(payload, bytes):
                    return response(url, content=payload)
                return response(url, payload=payload)
        raise requests.HTTPError(f"404 for {url}", response=response(url, status=404, content=b""))


def make_downloader(data_dir: Path, fake: FakeEdgar,
                    monkeypatch: pytest.MonkeyPatch) -> EdgarDownloader:
    """An EdgarDownloader whose HTTP calls all go to ``fake``."""
    client = EdgarClient(user_agent=TEST_AGENT, min_interval=0)
    monkeypatch.setattr(client, "get", fake)
    return EdgarDownloader(client, data_dir=data_dir)
