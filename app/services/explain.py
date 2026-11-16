"""Risk sonucundan okunabilir açıklama metni üretir.

Metin, saklanan sayılardan şablonla kurulur; böylece her cümlenin dayandığı değer
izlenebilir kalır.
"""
from __future__ import annotations

from app.services import risk_engine as re
from app.services.risk_engine import RiskResult

FACTOR_NAMES = {"hasar": "hasar şiddeti", "cevre": "çevresel koşullar", "zaman": "zamansal etkenler"}

SUB_FACTOR_NAMES = {
    "nem": "yüksek bağıl nem",
    "donma": "donma-çözülme döngüleri",
    "termal": "günlük sıcaklık farkı",
    "egilim": "hasarın son dönemde artması",
    "bakim": "son bakımın üzerinden geçen süre",
}

RECOMMENDATIONS = {
    "Kritik": "Öncelikli uzman incelemesi önerilir.",
    "Yüksek": "Kısa vadede kontrol önerilir.",
    "Orta": "Düzenli takip önerilir.",
    "Düşük": "Periyodik kontrol yeterlidir.",
    "Çok düşük": "Rutin gözlem yeterlidir.",
}

FLAG_TEXTS = {
    re.FLAG_NO_ENV_DATA: "Çevresel ölçüm bulunmadığı için çevresel puan hesaba katılmadı.",
    re.FLAG_PARTIAL_ENV_DATA: "Çevresel ölçümlerin bir kısmı eksik; çevresel puan mevcut verilerle hesaplandı.",
    re.FLAG_NO_TREND_DATA: "Hasar eğilimini hesaplamak için yeterli geçmiş kayıt yok.",
    re.FLAG_NO_MAINTENANCE: "Bakım kaydı bulunmadığı için bakım puanı en yüksek değerde alındı.",
    re.FLAG_NO_SEISMIC_SCENARIO: "Yapı için deprem senaryosu tanımlanmadığından sismik risk hesaplanmadı.",
    re.FLAG_SEVERITY_GUARD: "En yüksek şiddette bir hasar bulunduğu için sınıf en az 'Yüksek' olarak belirlendi.",
}

DISCLAIMER = "Bu çıktı karar destek amaçlıdır; restorasyon talimatı değildir."


def _fmt(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def dominant_factor(result: RiskResult) -> str:
    return max(result.contributions, key=result.contributions.get)


def dominant_sub_factor(result: RiskResult) -> str | None:
    """Baskın faktör çevre veya zaman ise onun en yüksek alt bileşeni."""
    parts = {"cevre": result.e_parts, "zaman": result.t_parts}.get(dominant_factor(result))
    if not parts:
        return None
    available = {k: v for k, v in parts.items() if v is not None}
    return max(available, key=available.get) if available else None


def build_explanation(result: RiskResult) -> str:
    c = result.contributions
    sentences = [
        f"Risk puanı {_fmt(result.r)} ({result.risk_class}).",
        (
            f"Kronik risk {_fmt(result.r_chronic)}: hasar {_fmt(c['hasar'])}, "
            f"çevre {_fmt(c['cevre'])}, zaman {_fmt(c['zaman'])} puan katkı yaptı."
        ),
    ]

    factor = dominant_factor(result)
    sub = dominant_sub_factor(result)
    if sub:
        sentences.append(
            f"En belirleyici etken {FACTOR_NAMES[factor]}; öne çıkan unsur {SUB_FACTOR_NAMES[sub]}."
        )
    else:
        sentences.append(f"En belirleyici etken {FACTOR_NAMES[factor]}.")

    if result.mu_d is not None:
        sentences.append(
            f"Sismik risk {_fmt(result.s)} (senaryo depreminde beklenen hasar derecesi "
            f"{_fmt(result.mu_d)}/5)."
        )

    sentences.extend(FLAG_TEXTS[f] for f in result.flags if f in FLAG_TEXTS)
    sentences.append(RECOMMENDATIONS[result.risk_class])
    sentences.append(DISCLAIMER)
    return " ".join(sentences)
