"""Shared fixtures: the fixture Universe downloaded through the fake EDGAR, and its chunk index."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from src.filings.edgar import EdgarDownloader
from src.rag import index
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


@pytest.fixture(scope="session")
def _built_index(tmp_path_factory) -> Path:
    """The fixture Universe's chunk index, embedded once per session (the slow part)."""
    root = tmp_path_factory.mktemp("built")
    with pytest.MonkeyPatch.context() as mp:
        downloader = make_downloader(root / "data", FakeEdgar(fu.routes()), mp)
        downloader.download_universe([fu.TICKER], since=date(2023, 1, 1))
        index.index_company(downloader, fu.TICKER, root / "index" / "chunks.db")
    return root / "index"


@pytest.fixture
def chunks_db(_built_index, tmp_path) -> Path:
    """A private copy of the fixture Universe's chunk index (SQLite and its Chroma folder)."""
    shutil.copytree(_built_index, tmp_path / "index")
    return tmp_path / "index" / "chunks.db"
