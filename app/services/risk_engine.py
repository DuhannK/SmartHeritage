"""Risk motoru: D, E, T, kronik risk, toplam risk ve sınıflandırma.

Bu modül veritabanına dokunmaz; yalnızca saf fonksiyonlar içerir. API de simülatör de
aynı fonksiyonları çağırır, böylece uygulama ile deneyler arasında fark oluşmaz.

Tanımların tamamı: proje dokümanı "02-risk-algoritmasi".
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Optional, Sequence

from app.config import DEFAULT_PARAMS, RISK_CLASSES, RiskParams
from app.services.seismic import seismic_score

# Veri eksikliği ve kural işaretleri
FLAG_NO_ENV_DATA = "cevresel_veri_yok"
FLAG_PARTIAL_ENV_DATA = "cevresel_veri_eksik"
FLAG_NO_TREND_DATA = "egilim_verisi_yetersiz"
FLAG_NO_MAINTENANCE = "bakim_kaydi_yok"
FLAG_NO_SEISMIC_SCENARIO = "sismik_senaryo_yok"
FLAG_SEVERITY_GUARD = "siddet_koruma_kurali"


@dataclass(frozen=True)
class DamageInput:
    type_code: str
    severity: int  # 1–5


@dataclass(frozen=True)
class Reading:
    timestamp: datetime
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None


@dataclass(frozen=True)
class EnvResult:
    value: Optional[float]  # hiç ölçüm yoksa None
    parts: dict  # {"nem": .., "donma": .., "termal": ..}; eksik olan None
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class TimeResult:
    value: float
    parts: dict  # {"egilim": .., "bakim": ..}
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskResult:
    d: float
    e: Optional[float]
    t: float
    s: float
    mu_d: Optional[float]
    r_chronic: float
    r_raw: float  # kırpılmamış Öklid normu; sıralama için
    r: float  # 0–100
    risk_class: str
    contributions: dict  # {"hasar": .., "cevre": .., "zaman": ..} kronik riske katkılar
    e_parts: dict
    t_parts: dict
    flags: tuple[str, ...]
    params_version: str = field(default="v1")


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------- D: hasar puanı


def damage_item_score(damage: DamageInput, params: RiskParams = DEFAULT_PARAMS) -> float:
    """Tek bir hasarın puanı: 20 × şiddet × tür ağırlığı (0–100)."""
    if not 1 <= damage.severity <= 5:
        raise ValueError("Hasar şiddeti 1 ile 5 arasında olmalıdır.")
    try:
        weight = params.damage_weights[damage.type_code]
    except KeyError:
        raise ValueError(f"Bilinmeyen hasar türü: {damage.type_code}") from None
    return 20.0 * damage.severity * weight


def damage_score(
    damages: Iterable[DamageInput], params: RiskParams = DEFAULT_PARAMS
) -> float:
    """Bileşenin hasar puanı: D = 100 × (1 − ∏(1 − dᵢ/100)).

    En büyük hasardan küçük olamaz, her yeni hasarla artar, 100'ü aşmaz.
    """
    remaining = 1.0
    for dmg in damages:
        remaining *= 1.0 - damage_item_score(dmg, params) / 100.0
    return 100.0 * (1.0 - remaining)


# ------------------------------------------------------------- E: çevresel puan


def _humidity_part(readings: Sequence[Reading], params: RiskParams) -> Optional[float]:
    values = [r.humidity_pct for r in readings if r.humidity_pct is not None]
    if not values:
        return None
    above = sum(1 for h in values if h > params.humidity_threshold_pct)
    return 100.0 * above / len(values)


def count_freeze_thaw_cycles(readings: Sequence[Reading]) -> Optional[int]:
    """0 °C'nin altından 0 °C ve üstüne her geçiş bir donma-çözülme döngüsüdür."""
    temps = [r.temperature_c for r in readings if r.temperature_c is not None]
    if not temps:
        return None
    cycles = 0
    frozen = temps[0] < 0
    for t in temps[1:]:
        if frozen and t >= 0:
            cycles += 1
        frozen = t < 0
    return cycles


def _thermal_part(readings: Sequence[Reading], params: RiskParams) -> Optional[float]:
    by_day: dict = defaultdict(list)
    for r in readings:
        if r.temperature_c is not None:
            by_day[r.timestamp.date()].append(r.temperature_c)
    ranges = [max(v) - min(v) for v in by_day.values() if len(v) >= 2]
    if not ranges:
        return None
    mean_range = sum(ranges) / len(ranges)
    return _clamp(100.0 * mean_range / params.thermal_max_range_c)


def environmental_score(
    readings: Iterable[Reading], as_of: datetime, params: RiskParams = DEFAULT_PARAMS
) -> EnvResult:
    """Son `env_window_days` günün ölçümlerinden çevresel puan.

    Eksik alt puan dışarıda bırakılır ve ağırlıklar yeniden ölçeklenir.
    """
    start = as_of - timedelta(days=params.env_window_days)
    window = sorted(
        (r for r in readings if start < r.timestamp <= as_of), key=lambda r: r.timestamp
    )

    cycles = count_freeze_thaw_cycles(window)
    parts = {
        "nem": _humidity_part(window, params),
        "donma": None
        if cycles is None
        else _clamp(100.0 * cycles / params.freeze_thaw_max_cycles),
        "termal": _thermal_part(window, params),
    }
    weights = {
        "nem": params.w_humidity,
        "donma": params.w_freeze_thaw,
        "termal": params.w_thermal,
    }
    available = {k: v for k, v in parts.items() if v is not None}
    if not available:
        return EnvResult(None, parts, (FLAG_NO_ENV_DATA,))

    total_w = sum(weights[k] for k in available)
    value = sum(weights[k] * v for k, v in available.items()) / total_w
    flags = (FLAG_PARTIAL_ENV_DATA,) if len(available) < len(parts) else ()
    return EnvResult(value, parts, flags)


# ------------------------------------------------------------- T: zamansal puan


def temporal_score(
    d_now: float,
    d_past: Optional[float],
    months_since_maintenance: Optional[float],
    params: RiskParams = DEFAULT_PARAMS,
) -> TimeResult:
    """Zamansal puan: T = w_trend × Eğilim + w_maintenance × Bakım.

    d_past: `trend_window_days` gün önceki hasar puanı; o tarihte kayıt yoksa None.
    months_since_maintenance: hiç bakım kaydı yoksa None.
    """
    flags = []
    if d_past is None:
        trend = 0.0
        flags.append(FLAG_NO_TREND_DATA)
    else:
        trend = _clamp(100.0 * (d_now - d_past) / params.trend_max_increase)

    if months_since_maintenance is None:
        maintenance = 100.0
        flags.append(FLAG_NO_MAINTENANCE)
    else:
        if months_since_maintenance < 0:
            raise ValueError("Bakımdan beri geçen süre negatif olamaz.")
        maintenance = _clamp(
            100.0 * months_since_maintenance / params.maintenance_max_months
        )

    value = params.w_trend * trend + params.w_maintenance * maintenance
    return TimeResult(value, {"egilim": trend, "bakim": maintenance}, tuple(flags))


# ------------------------------------------------------ birleştirme ve sınıflar


def chronic_risk(
    d: float, e: Optional[float], t: float, params: RiskParams = DEFAULT_PARAMS
) -> tuple[float, dict]:
    """R_kronik = w_d·D + w_e·E + w_t·T ve her faktörün katkısı.

    E hesaplanamadıysa (None) D ve T ağırlıkları yeniden ölçeklenir.
    """
    if e is None:
        total = params.w_damage + params.w_time
        contributions = {
            "hasar": params.w_damage / total * d,
            "cevre": 0.0,
            "zaman": params.w_time / total * t,
        }
    else:
        contributions = {
            "hasar": params.w_damage * d,
            "cevre": params.w_env * e,
            "zaman": params.w_time * t,
        }
    return sum(contributions.values()), contributions


def total_risk(r_chronic: float, s: float) -> tuple[float, float]:
    """Kronik ve sismik riskin Öklid normu: (kırpılmamış, 0–100'e kırpılmış)."""
    raw = math.hypot(r_chronic, s)
    return raw, min(100.0, raw)


def _class_rank(name: str) -> int:
    return [c[0] for c in RISK_CLASSES].index(name)


def classify(
    r: float, max_severity: int = 0, params: RiskParams = DEFAULT_PARAMS
) -> tuple[str, bool]:
    """Risk sınıfı ve koruma kuralının devreye girip girmediği."""
    name = next(c for c, lower in RISK_CLASSES if r >= lower)
    if (
        params.severity_guard_enabled
        and max_severity >= params.severity_guard_level
        and _class_rank(name) > _class_rank(params.severity_guard_min_class)
    ):
        return params.severity_guard_min_class, True
    return name, False


def assess(
    damages: Sequence[DamageInput],
    readings: Iterable[Reading],
    as_of: datetime,
    d_past: Optional[float],
    months_since_maintenance: Optional[float],
    base_vulnerability: float,
    scenario_intensity: Optional[float],
    params: RiskParams = DEFAULT_PARAMS,
) -> RiskResult:
    """Bir bileşenin `as_of` anındaki tam risk değerlendirmesi."""
    d = damage_score(damages, params)
    env = environmental_score(readings, as_of, params)
    tim = temporal_score(d, d_past, months_since_maintenance, params)
    r_chronic, contributions = chronic_risk(d, env.value, tim.value, params)

    s, mu_d = seismic_score(scenario_intensity, base_vulnerability, d, params)
    r_raw, r = total_risk(r_chronic, s)

    max_severity = max((dmg.severity for dmg in damages), default=0)
    risk_class, guard_applied = classify(r, max_severity, params)

    flags = list(env.flags) + list(tim.flags)
    if scenario_intensity is None:
        flags.append(FLAG_NO_SEISMIC_SCENARIO)
    if guard_applied:
        flags.append(FLAG_SEVERITY_GUARD)

    return RiskResult(
        d=d,
        e=env.value,
        t=tim.value,
        s=s,
        mu_d=mu_d,
        r_chronic=r_chronic,
        r_raw=r_raw,
        r=r,
        risk_class=risk_class,
        contributions=contributions,
        e_parts=env.parts,
        t_parts=tim.parts,
        flags=tuple(flags),
        params_version=params.version,
    )
