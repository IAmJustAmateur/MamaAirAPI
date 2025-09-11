# api/services/aggregation.py
import math
from typing import Mapping, Optional


def _sigma(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def agg_max_plus_logistic_tail(
    risks: Mapping[str, float],
    *,
    Rmax: float = 10.0,
    weights: Optional[Mapping[str, float]] = None,
    # Новые «человечные» параметры:
    ref: float = 1.5,  # «умеренный» риск → шаг в лог-шкале = log(ref)
    mid: float = 3.0,  # середина S-кривой ≈ на 'mid' умеренных факторах
    sensitivity: float = 1.0  # чувствительность (0.5 → плавнее; 1.5 → агрессивнее)
) -> float:
    """
    Интегральный риск = m + (Rmax - m) * g(T),
      m = max(r_i)
      T = sum_{i != argmax} w_i * max(log(r_i), 0)
      g(T) — логистика, нормированная так, что g(0)=0 и g(∞)=1.

    Свойства:
      - все r_i <= 1 → 1.0
      - только один пик m>1 → m
      - рост S-образный, не превышает Rmax, управляется ref/mid/sensitivity.
    """
    vals = {k: float(v) for k, v in risks.items() if v is not None and v > 0}
    if not vals:
        return 1.0

    m = max(vals.values())
    if m <= 1.0 and all(v <= 1.0 for v in vals.values()):
        return 1.0

    w = weights or {}
    max_key = max(vals, key=lambda kk: vals[kk])

    # сумма вкладов только от вторичных r>1
    T = 0.0
    for key, v in vals.items():
        if key == max_key:
            continue
        if v > 1.0:
            T += float(w.get(key, 1.0)) * math.log(v)

    if T <= 0.0:
        return m

    # Пересчёт «человечных» настроек в (b, k)
    # k — горизонтальный масштаб логистики; sensitivity<1 → k больше → кривая плавнее
    step = max(math.log(max(ref, 1.0000001)), 1e-12)  # шаг = log(ref)
    k = step / max(sensitivity, 1e-6)
    b = mid * step

    base = _sigma((-b) / k)  # значение при T=0
    s = _sigma((T - b) / k)
    g = (s - base) / (1.0 - base)  # g(0)=0, g→1

    return m + (Rmax - m) * max(0.0, min(1.0, g))
