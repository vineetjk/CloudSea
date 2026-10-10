import pandas as pd
import pytest

from cloudsea import label


def dawn(**overrides) -> pd.DataFrame:
    row = {"n_dawn": 5, "n_with_sky": 5, "low_layer_reports": 0, "fog_or_vis1k_reports": 0,
           "deck_near_summit_reports": 0, "precip_reports": 0, "rh850": 60.0}
    row.update(overrides)
    return pd.DataFrame([row], index=pd.to_datetime(["2025-01-09"]))


def value(name: str, **overrides):
    return label.label(dawn(**overrides), name).iloc[0]


def test_low_layer_in_two_reports_without_rain_is_a_sea():
    assert value("B_low_layer_summit_clear", low_layer_reports=2) == 1


def test_one_report_is_not_enough():
    assert value("B_low_layer_summit_clear", low_layer_reports=1) == 0


def test_rain_cancels_it():
    assert value("B_low_layer_summit_clear", low_layer_reports=4, precip_reports=1) == 0


def test_saturated_summit_air_means_summit_is_inside_the_cloud():
    assert value("A_low_layer", low_layer_reports=4, rh850=95.0) == 1
    assert value("B_low_layer_summit_clear", low_layer_reports=4, rh850=95.0) == 0


def test_too_few_reports_is_unknown_not_false():
    assert pd.isna(value("B_low_layer_summit_clear", n_dawn=2, low_layer_reports=2))


def test_missing_atmosphere_is_unknown_for_b_but_not_a():
    assert pd.isna(value("B_low_layer_summit_clear", low_layer_reports=3, rh850=float("nan")))
    assert value("A_low_layer", low_layer_reports=3, rh850=float("nan")) == 1


def test_strict_needs_fog_and_no_deck_at_summit():
    assert value("C_strict", fog_or_vis1k_reports=2) == 1
    assert value("C_strict", fog_or_vis1k_reports=2, deck_near_summit_reports=1) == 0


@pytest.mark.parametrize("reported_m,counts", [(1500, False), (1400, True), (1000, False), (900, True)])
def test_visibility_thresholds_survive_mile_rounding(reported_m, counts):
    from cloudsea import metar
    vis_m = round(reported_m / metar.MILE_M, 2) * metar.MILE_M  # what IEM's 2-decimal miles turn into
    threshold = metar.VIS_LOW_M if reported_m >= 1400 else metar.VIS_FOG_M
    assert (vis_m < threshold) is counts
