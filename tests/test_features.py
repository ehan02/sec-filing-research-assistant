"""The batch feature job on the fixture Universe."""

from __future__ import annotations

import pandas as pd
import pytest

from src.agents.tools import section_diff
from src.features.filing_features import build_features, write_features
from tests import fixture_universe as fu


@pytest.fixture
def features(universe):
    return build_features(universe.downloader)


def test_one_row_per_original_10k_keyed_by_cik_accession_and_availability(features):
    assert list(features["accession_no"]) == [fu.ACC_10K_2022, fu.ACC_10K_2023]  # no 10-K/A row
    assert list(features["cik"]) == [fu.CIK, fu.CIK]
    assert list(features["availability_time"]) == [fu.AVAILABILITY[fu.ACC_10K_2022],
                                                   fu.AVAILABILITY[fu.ACC_10K_2023]]
    assert list(features["fiscal_year"]) == [2022, 2023]


def test_prior_comparison_never_uses_a_later_filing(features):
    first, second = features.iloc[0], features.iloc[1]
    # FY2022's only other 10-K was accepted later, so it has no prior: null, not a skipped row.
    assert pd.isna(first["prior_accession_no"])
    assert pd.isna(first["item_1a_similarity"]) and pd.isna(first["risk_factor_count_change"])
    assert second["prior_accession_no"] == fu.ACC_10K_2022
    for _, row in features.dropna(subset=["prior_accession_no"]).iterrows():
        assert fu.AVAILABILITY[row["prior_accession_no"]] <= row["availability_time"]


def test_similarity_matches_section_diff_and_risk_factors_are_counted(universe, features):
    second = features.iloc[1]
    diff = section_diff(fu.TICKER, "Item 1A", "10-K", 2022, 2023, downloader=universe.downloader)
    assert second["item_1a_similarity"] == pytest.approx(diff["similarity"])
    assert 0 < second["item_7_similarity"] < 1
    # Bold sentences in Item 1A are risk factors; the bold category heading is not.
    assert list(features["risk_factor_count"]) == [3, 4]
    assert second["risk_factor_count_change"] == 1
    assert (features["item_1a_words"] > 0).all() and (features["item_7_words"] > 0).all()


def test_rerunning_the_job_writes_identical_output(universe, tmp_path):
    a, b = tmp_path / "a.parquet", tmp_path / "b.parquet"
    write_features(universe.downloader, a)
    write_features(universe.downloader, b)
    assert a.read_bytes() == b.read_bytes()
    pd.testing.assert_frame_equal(pd.read_parquet(a), build_features(universe.downloader))
