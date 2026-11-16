"""Analitik Hiyerarşi Süreci (AHP): ikili karşılaştırma matrisinden ağırlık ve tutarlılık.

Kronik risk ağırlıklarının (0.50 / 0.30 / 0.20) gerekçesini raporda göstermek için
kullanılır. Yargılar ekip yargısıdır; uzman paneli sonucu değildir.
"""
from __future__ import annotations

import math
from typing import Sequence

# Saaty'nin rastgele tutarlılık indeksleri (n = 1..10)
RANDOM_INDEX = (0.0, 0.0, 0.58, 0.90, 1.12, 1.24, 1.32, 1.41, 1.45, 1.49)

# Yargılar: hasar çevreden 2 kat, zamandan 3 kat; çevre zamandan 2 kat önemli.
# Sıra: hasar (D), çevre (E), zaman (T)
CHRONIC_RISK_MATRIX = (
    (1.0, 2.0, 3.0),
    (1 / 2, 1.0, 2.0),
    (1 / 3, 1 / 2, 1.0),
)


def ahp_weights(matrix: Sequence[Sequence[float]]) -> tuple[list[float], float]:
    """Geometrik ortalama yöntemiyle ağırlıklar ve tutarlılık oranı (CR).

    CR < 0.10 ise yargılar tutarlı kabul edilir.
    """
    n = len(matrix)
    if any(len(row) != n for row in matrix):
        raise ValueError("Matris kare olmalıdır.")
    if n > len(RANDOM_INDEX):
        raise ValueError("En fazla 10 ölçüt desteklenir.")

    geo = [math.prod(row) ** (1.0 / n) for row in matrix]
    total = sum(geo)
    weights = [g / total for g in geo]

    if n <= 2:
        return weights, 0.0
    lambda_max = sum(
        sum(matrix[i][j] * weights[j] for j in range(n)) / weights[i] for i in range(n)
    ) / n
    ci = (lambda_max - n) / (n - 1)
    return weights, ci / RANDOM_INDEX[n - 1]
