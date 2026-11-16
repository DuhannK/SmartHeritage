"""Sürümlü risk parametreleri.

Buradaki tüm sayılar prototipin başlangıç parametreleridir; evrensel kabul görmüş
restorasyon standartları değildir. Her risk kaydı hangi parametre sürümüyle
hesaplandığını saklar, böylece duyarlılık deneyleri izlenebilir kalır.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


def _frozen(d: dict) -> Mapping:
    return MappingProxyType(dict(d))


# Hasar türü kodu -> (görünen ad, ağırlık)
DAMAGE_TYPES: Mapping[str, tuple[str, float]] = _frozen(
    {
        "yapisal_catlak": ("Yapısal çatlak", 1.0),
        "malzeme_kaybi": ("Malzeme kaybı / bozulma", 0.9),
        "nem_rutubet": ("Nem ve rutubet", 0.7),
        "yuzey_asinmasi": ("Yüzey aşınması", 0.6),
        "biyolojik_olusum": ("Biyolojik oluşum", 0.5),
        "renk_degisimi": ("Renk değişimi", 0.3),
    }
)

# Yığma tipi -> (görünen ad, kırılganlık indeksi V)
# Değerler: Giovinazzi & Lagomarsino (2004), Tablo 5, en olası değerler.
MASONRY_TYPOLOGIES: Mapping[str, tuple[str, float]] = _frozen(
    {
        "moloz_tas": ("Moloz taş", 0.873),
        "basit_tas": ("Basit taş", 0.74),
        "masif_tas": ("Masif taş", 0.616),
    }
)

# Sınıf adı ve alt sınırı (dahil), büyükten küçüğe. Eşikler: Ortiz & Ortiz (2016).
RISK_CLASSES: tuple[tuple[str, float], ...] = (
    ("Kritik", 75.0),
    ("Yüksek", 50.0),
    ("Orta", 25.0),
    ("Düşük", 10.0),
    ("Çok düşük", 0.0),
)


@dataclass(frozen=True)
class RiskParams:
    version: str = "v1"

    # Hasar puanı D
    damage_weights: Mapping[str, float] = field(
        default_factory=lambda: _frozen({k: v[1] for k, v in DAMAGE_TYPES.items()})
    )

    # Çevresel puan E
    env_window_days: int = 30
    w_humidity: float = 0.45
    w_freeze_thaw: float = 0.35
    w_thermal: float = 0.20
    humidity_threshold_pct: float = 75.0
    freeze_thaw_max_cycles: float = 15.0
    thermal_max_range_c: float = 20.0

    # Zamansal puan T
    trend_window_days: int = 90
    trend_max_increase: float = 30.0
    maintenance_max_months: float = 60.0
    w_trend: float = 0.6
    w_maintenance: float = 0.4

    # Kronik risk ağırlıkları (AHP gerekçesi: app/services/ahp.py)
    w_damage: float = 0.50
    w_env: float = 0.30
    w_time: float = 0.20

    # Sismik
    typology_vulnerability: Mapping[str, float] = field(
        default_factory=lambda: _frozen({k: v[1] for k, v in MASONRY_TYPOLOGIES.items()})
    )
    damage_vulnerability_gain: float = 0.10  # V = V_tip + gain * D/100 (varsayım)
    inspection_min_mu_d: float = 0.5  # bu değerin altında deprem sonrası işaret üretilmez

    # Koruma kuralı: şiddeti bu değere ulaşan hasar varsa sınıf en az "Yüksek"
    severity_guard_enabled: bool = True
    severity_guard_level: int = 5
    severity_guard_min_class: str = "Yüksek"


DEFAULT_PARAMS = RiskParams()
