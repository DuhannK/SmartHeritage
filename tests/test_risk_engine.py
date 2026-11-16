from datetime import datetime, timedelta

import pytest

from app.config import DEFAULT_PARAMS, RiskParams
from app.services import risk_engine as re
from app.services.risk_engine import DamageInput, Reading

AS_OF = datetime(2026, 1, 31, 12, 0)


def hourly(day_offset, hour, temp=None, hum=None):
    ts = AS_OF.replace(hour=0) - timedelta(days=day_offset) + timedelta(hours=hour)
    return Reading(ts, temp, hum)


# ---------------------------------------------------------------- D


def test_single_damage_score():
    assert re.damage_item_score(DamageInput("yapisal_catlak", 4)) == pytest.approx(80.0)
    assert re.damage_item_score(DamageInput("renk_degisimi", 5)) == pytest.approx(30.0)


def test_damage_score_combines_two_damages():
    damages = [DamageInput("yapisal_catlak", 4), DamageInput("nem_rutubet", 3)]
    assert re.damage_score(damages) == pytest.approx(88.4)


def test_damage_score_empty_is_zero():
    assert re.damage_score([]) == 0.0


def test_damage_score_never_below_largest_and_never_above_100():
    damages = [DamageInput("yapisal_catlak", 5)] + [DamageInput("malzeme_kaybi", 5)] * 3
    d = re.damage_score(damages)
    assert d == pytest.approx(100.0)
    one = re.damage_score([DamageInput("yuzey_asinmasi", 3)])
    two = re.damage_score([DamageInput("yuzey_asinmasi", 3), DamageInput("renk_degisimi", 1)])
    assert two > one


@pytest.mark.parametrize("severity", [0, 6, -1])
def test_invalid_severity_rejected(severity):
    with pytest.raises(ValueError):
        re.damage_score([DamageInput("yapisal_catlak", severity)])


def test_unknown_damage_type_rejected():
    with pytest.raises(ValueError):
        re.damage_score([DamageInput("bilinmeyen", 3)])


# ---------------------------------------------------------------- E


def test_humidity_part_is_share_above_threshold():
    readings = [hourly(1, h, hum=80) for h in range(3)] + [hourly(1, 5, hum=60)]
    env = re.environmental_score(readings, AS_OF)
    assert env.parts["nem"] == pytest.approx(75.0)
    assert env.parts["donma"] is None and env.parts["termal"] is None
    assert env.value == pytest.approx(75.0)  # tek alt puan, ağırlık yeniden ölçeklenir
    assert re.FLAG_PARTIAL_ENV_DATA in env.flags


def test_freeze_thaw_cycles_counted():
    temps = [-2, 3, -1, 4, 5, -3, 1]
    readings = [hourly(2, h, temp=t) for h, t in enumerate(temps)]
    assert re.count_freeze_thaw_cycles(readings) == 3
    env = re.environmental_score(readings, AS_OF)
    assert env.parts["donma"] == pytest.approx(20.0)  # 3 / 15


def test_thermal_part_uses_mean_daily_range():
    readings = [hourly(1, 4, temp=5), hourly(1, 14, temp=15), hourly(2, 4, temp=10), hourly(2, 14, temp=30)]
    env = re.environmental_score(readings, AS_OF)
    assert env.parts["termal"] == pytest.approx(75.0)  # ortalama fark 15 / 20


def test_environmental_score_full_weights():
    readings = [
        hourly(1, 4, temp=5, hum=80),
        hourly(1, 14, temp=15, hum=60),
    ]
    env = re.environmental_score(readings, AS_OF)
    expected = 0.45 * 50 + 0.35 * 0 + 0.20 * 50
    assert env.value == pytest.approx(expected)
    assert env.flags == ()


def test_readings_outside_window_ignored():
    old = [hourly(45, 3, temp=10, hum=99)]
    env = re.environmental_score(old, AS_OF)
    assert env.value is None
    assert env.flags == (re.FLAG_NO_ENV_DATA,)


# ---------------------------------------------------------------- T


def test_temporal_score_example():
    t = re.temporal_score(d_now=62, d_past=50, months_since_maintenance=36)
    assert t.parts == {"egilim": pytest.approx(40.0), "bakim": pytest.approx(60.0)}
    assert t.value == pytest.approx(48.0)


def test_temporal_score_decreasing_damage_gives_zero_trend():
    assert re.temporal_score(40, 60, 0).value == 0.0


def test_temporal_score_missing_history_and_maintenance():
    t = re.temporal_score(50, None, None)
    assert t.parts == {"egilim": 0.0, "bakim": 100.0}
    assert set(t.flags) == {re.FLAG_NO_TREND_DATA, re.FLAG_NO_MAINTENANCE}


def test_temporal_score_caps_at_100():
    assert re.temporal_score(90, 10, 240).value == pytest.approx(100.0)


# ---------------------------------------------------------------- birleştirme


def test_chronic_risk_weights():
    r, c = re.chronic_risk(80, 70, 60)
    assert r == pytest.approx(73.0)
    assert c == {"hasar": pytest.approx(40.0), "cevre": pytest.approx(21.0), "zaman": pytest.approx(12.0)}


def test_chronic_risk_without_env_rescales():
    r, c = re.chronic_risk(70, None, 0)
    assert r == pytest.approx(50.0)  # 0.5/0.7 × 70
    assert c["cevre"] == 0.0


def test_total_risk_is_euclidean_norm_and_clipped():
    assert re.total_risk(30, 40) == (pytest.approx(50.0), pytest.approx(50.0))
    raw, clipped = re.total_risk(90, 80)
    assert raw > 100 and clipped == 100.0
    assert re.total_risk(64, 0)[1] == pytest.approx(64.0)


@pytest.mark.parametrize(
    "r, expected",
    [(0, "Çok düşük"), (9.99, "Çok düşük"), (10, "Düşük"), (25, "Orta"), (49.9, "Orta"), (50, "Yüksek"), (75, "Kritik"), (100, "Kritik")],
)
def test_class_thresholds(r, expected):
    assert re.classify(r) == (expected, False)


def test_severity_guard_raises_class():
    assert re.classify(30, max_severity=5) == ("Yüksek", True)
    assert re.classify(80, max_severity=5) == ("Kritik", False)
    assert re.classify(30, max_severity=4) == ("Orta", False)


def test_severity_guard_can_be_disabled():
    params = RiskParams(severity_guard_enabled=False)
    assert re.classify(30, max_severity=5, params=params) == ("Orta", False)


# ---------------------------------------------------------------- assess


def test_assess_end_to_end():
    damages = [DamageInput("yapisal_catlak", 4), DamageInput("nem_rutubet", 3)]
    readings = [hourly(1, 4, temp=5, hum=80), hourly(1, 14, temp=15, hum=60)]
    result = re.assess(
        damages=damages,
        readings=readings,
        as_of=AS_OF,
        d_past=76.4,
        months_since_maintenance=36,
        base_vulnerability=0.616,
        scenario_intensity=8,
    )
    assert result.d == pytest.approx(88.4)
    assert result.e == pytest.approx(32.5)
    assert result.t == pytest.approx(48.0)
    assert result.r_chronic == pytest.approx(0.5 * 88.4 + 0.3 * 32.5 + 0.2 * 48.0)
    assert result.r == pytest.approx((result.r_chronic**2 + result.s**2) ** 0.5)
    assert result.risk_class == "Yüksek"
    assert result.flags == ()
    assert result.params_version == DEFAULT_PARAMS.version


def test_assess_with_no_data_flags_everything():
    result = re.assess([], [], AS_OF, None, None, 0.616, None)
    assert result.d == 0.0 and result.e is None and result.s == 0.0
    assert set(result.flags) == {
        re.FLAG_NO_ENV_DATA,
        re.FLAG_NO_TREND_DATA,
        re.FLAG_NO_MAINTENANCE,
        re.FLAG_NO_SEISMIC_SCENARIO,
    }
    # Bakım kaydı yok: T = 40, yeniden ölçeklenmiş katkı 0.2/0.7 × 40
    assert result.r == pytest.approx(0.2 / 0.7 * 40)


def test_collapsed_component_is_critical_regardless_of_environment():
    """Deprem sonrası göçen bileşen: gerçek hasar D üzerinden tam ağırlıkla yansır."""
    damages = [DamageInput("yapisal_catlak", 5)]
    result = re.assess(damages, [], AS_OF, d_past=20, months_since_maintenance=1,
                       base_vulnerability=0.616, scenario_intensity=8)
    assert result.d == pytest.approx(100.0)
    assert result.risk_class == "Kritik"
