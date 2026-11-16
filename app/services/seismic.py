"""Makrosismik hasar modeli.

Kaynak: Giovinazzi, S., & Lagomarsino, S. (2004). A macroseismic method for the
vulnerability assessment of buildings. 13th WCEE, Paper No. 896.

Sınır: yöntem sıradan binalar için geliştirilmiştir. Sur ve burç gibi yapılar için
kalibre edilmemiştir; burada yaklaşık bir senaryo modeli olarak kullanılır.

Bu modül veritabanına dokunmaz; yalnızca saf fonksiyonlar içerir.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional

from app.config import DEFAULT_PARAMS, RiskParams

MAX_DAMAGE_GRADE = 5


def mean_damage_grade(intensity: float, vulnerability: float) -> float:
    """Beklenen ortalama hasar derecesi μD (0 = hasarsız, 5 = göçme).

    intensity: yapının bulunduğu yerdeki şiddet (EMS-98, 1–12). Büyüklük (Mw) değildir.
    vulnerability: kırılganlık indeksi V.
    """
    if not 1 <= intensity <= 12:
        raise ValueError("Deprem şiddeti 1 ile 12 arasında olmalıdır (EMS-98).")
    return 2.5 * (1.0 + math.tanh((intensity + 6.25 * vulnerability - 13.1) / 2.3))


def effective_vulnerability(
    base_vulnerability: float, damage_score: float, params: RiskParams = DEFAULT_PARAMS
) -> float:
    """Mevcut hasarın kırılganlığı artırdığı varsayımı: V = V_tip + gain × D/100."""
    d = min(max(damage_score, 0.0), 100.0)
    return base_vulnerability + params.damage_vulnerability_gain * d / 100.0


def seismic_score(
    intensity: Optional[float],
    base_vulnerability: float,
    damage_score: float,
    params: RiskParams = DEFAULT_PARAMS,
) -> tuple[float, Optional[float]]:
    """Sismik risk puanı S (0–100) ve μD. Senaryo şiddeti yoksa (0.0, None) döner."""
    if intensity is None:
        return 0.0, None
    v = effective_vulnerability(base_vulnerability, damage_score, params)
    mu_d = mean_damage_grade(intensity, v)
    return 20.0 * mu_d, mu_d


def damage_grade_probabilities(mu_d: float) -> list[float]:
    """Hasar derecesi 0..5 için olasılıklar: Binom(5, μD/5).

    Simülatörde bir bileşenin depremdeki gerçek hasar derecesini çekmek için kullanılır.
    """
    p = min(max(mu_d / MAX_DAMAGE_GRADE, 0.0), 1.0)
    n = MAX_DAMAGE_GRADE
    return [math.comb(n, k) * p**k * (1 - p) ** (n - k) for k in range(n + 1)]


@dataclass(frozen=True)
class ComponentSeismicInput:
    component_id: int
    base_vulnerability: float
    damage_score: float


@dataclass(frozen=True)
class InspectionItem:
    component_id: int
    mu_d: float
    needs_inspection: bool


def inspection_queue(
    components: Iterable[ComponentSeismicInput],
    intensity: float,
    params: RiskParams = DEFAULT_PARAMS,
) -> list[InspectionItem]:
    """Deprem sonrası denetim sırası: beklenen hasarı en yüksek bileşen en başta."""
    items = []
    for c in components:
        v = effective_vulnerability(c.base_vulnerability, c.damage_score, params)
        mu_d = mean_damage_grade(intensity, v)
        items.append(
            InspectionItem(c.component_id, mu_d, mu_d >= params.inspection_min_mu_d)
        )
    return sorted(items, key=lambda i: (-i.mu_d, i.component_id))
