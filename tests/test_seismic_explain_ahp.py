from datetime import datetime

import pytest

from app.config import DEFAULT_PARAMS
from app.services import risk_engine as re
from app.services import seismic
from app.services.ahp import CHRONIC_RISK_MATRIX, ahp_weights
from app.services.explain import DISCLAIMER, build_explanation, dominant_factor
from app.services.risk_engine import DamageInput
from app.services.seismic import ComponentSeismicInput

MASSIVE, RUBBLE = 0.616, 0.873


# ---------------------------------------------------------------- sismik


@pytest.mark.parametrize(
    "intensity, expected",
    [(6, 0.27), (7, 0.62), (8, 1.26), (9, 2.23), (10, 3.29)],
)
def test_mean_damage_grade_massive_stone(intensity, expected):
    assert seismic.mean_damage_grade(intensity, MASSIVE) == pytest.approx(expected, abs=0.01)


def test_mean_damage_grade_bounds_and_monotonic():
    values = [seismic.mean_damage_grade(i, RUBBLE) for i in range(1, 13)]
    assert all(0 <= v <= 5 for v in values)
    assert values == sorted(values)
    assert seismic.mean_damage_grade(8, RUBBLE) > seismic.mean_damage_grade(8, MASSIVE)


@pytest.mark.parametrize("intensity", [0, 13, -3])
def test_invalid_intensity_rejected(intensity):
    with pytest.raises(ValueError):
        seismic.mean_damage_grade(intensity, MASSIVE)


def test_existing_damage_increases_vulnerability():
    assert seismic.effective_vulnerability(MASSIVE, 0) == pytest.approx(0.616)
    assert seismic.effective_vulnerability(MASSIVE, 100) == pytest.approx(0.716)
    s_healthy, _ = seismic.seismic_score(8, MASSIVE, 0)
    s_damaged, _ = seismic.seismic_score(8, MASSIVE, 80)
    assert s_damaged > s_healthy


def test_seismic_score_without_scenario():
    assert seismic.seismic_score(None, MASSIVE, 50) == (0.0, None)


def test_seismic_score_is_20_times_mu_d():
    s, mu_d = seismic.seismic_score(9, MASSIVE, 0)
    assert s == pytest.approx(20 * mu_d)


def test_damage_grade_probabilities():
    probs = seismic.damage_grade_probabilities(2.5)
    assert len(probs) == 6
    assert sum(probs) == pytest.approx(1.0)
    assert sum(k * p for k, p in enumerate(probs)) == pytest.approx(2.5)
    assert seismic.damage_grade_probabilities(0)[0] == 1.0
    assert seismic.damage_grade_probabilities(5)[5] == 1.0


def test_inspection_queue_orders_by_expected_damage():
    components = [
        ComponentSeismicInput(1, MASSIVE, 0),
        ComponentSeismicInput(2, RUBBLE, 60),
        ComponentSeismicInput(3, MASSIVE, 90),
    ]
    queue = seismic.inspection_queue(components, intensity=8)
    assert [i.component_id for i in queue] == [2, 3, 1]
    assert all(i.needs_inspection for i in queue)


def test_weak_earthquake_does_not_flag_robust_components():
    queue = seismic.inspection_queue([ComponentSeismicInput(1, MASSIVE, 0)], intensity=6)
    assert queue[0].mu_d < DEFAULT_PARAMS.inspection_min_mu_d
    assert not queue[0].needs_inspection


# ---------------------------------------------------------------- açıklama


def _result(**kw):
    defaults = dict(
        damages=[DamageInput("yapisal_catlak", 4)],
        readings=[],
        as_of=datetime(2026, 1, 31),
        d_past=70,
        months_since_maintenance=12,
        base_vulnerability=MASSIVE,
        scenario_intensity=8,
    )
    defaults.update(kw)
    return re.assess(**defaults)


def test_explanation_contains_score_class_and_disclaimer():
    result = _result()
    text = build_explanation(result)
    assert f"({result.risk_class})" in text
    assert "hasar şiddeti" in text
    assert "Sismik risk" in text
    assert text.endswith(DISCLAIMER)


def test_explanation_mentions_missing_data_and_guard():
    result = _result(damages=[DamageInput("renk_degisimi", 5)], d_past=None,
                     months_since_maintenance=None, scenario_intensity=None)
    text = build_explanation(result)
    assert re.FLAG_SEVERITY_GUARD in result.flags
    assert "en az 'Yüksek'" in text
    assert "Bakım kaydı bulunmadığı" in text
    assert "deprem senaryosu tanımlanmadığından" in text
    assert "Sismik risk" not in text.split("deprem senaryosu")[0]


def test_dominant_factor_can_be_time():
    result = _result(damages=[DamageInput("renk_degisimi", 1)], d_past=None,
                     months_since_maintenance=None)
    assert dominant_factor(result) == "zaman"
    assert "son bakımın üzerinden geçen süre" in build_explanation(result)


# ---------------------------------------------------------------- AHP


def test_ahp_reproduces_chronic_weights():
    weights, cr = ahp_weights(CHRONIC_RISK_MATRIX)
    assert weights == pytest.approx([0.540, 0.297, 0.163], abs=0.002)
    assert sum(weights) == pytest.approx(1.0)
    assert 0 <= cr < 0.10


def test_ahp_equal_judgments_give_equal_weights():
    weights, cr = ahp_weights([[1, 1], [1, 1]])
    assert weights == pytest.approx([0.5, 0.5])
    assert cr == 0.0
