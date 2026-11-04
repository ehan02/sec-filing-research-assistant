"""Shared fixtures: the fixture Universe downloaded through the fake EDGAR."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from src.filings.edgar import EdgarDownloader
from tests import fixture_universe as fu
from tests.fakes import FakeEdgar, make_downloader


@dataclass
class Universe:
    """A downloaded fixture Universe: its data directory, downloader and fake EDGAR."""

    data_dir: Path
    downloader: EdgarDownloader
    fake: FakeEdgar


@pytest.fixture
def universe(tmp_path, monkeypatch) -> Universe:
    """Fixture Corp's Filings and companyfacts, downloaded into ``tmp_path``.

    See ``tests/fixture_universe.py`` for what the Universe contains.
    """
    fake = FakeEdgar(fu.routes())
    downloader = make_downloader(tmp_path, fake, monkeypatch)
    summary = downloader.download_universe([fu.TICKER], since=date(2023, 1, 1))
    assert summary[fu.TICKER]["failed"] == 0, summary
    return Universe(data_dir=tmp_path, downloader=downloader, fake=fake)
