# api/services/risk_engine.py

from __future__ import annotations

import logging
from typing import Any, Iterable, Sequence, Mapping

logger = logging.getLogger(__name__)


def calculate_risks(
    risks: Iterable[Any],
    fields: Sequence[str],
    obj: Any,
    RiskModel: type,  # класс модели передаём снаружи, чтобы не тянуть его импортом
) -> dict[str, float]:
    """
    Calculate risk factors based on given object and risk factors.

    Args:
        risks (Iterable): Risk definitions to calculate.
        fields (Sequence[str]): Fields of object that are used in risk factor conditions.
        obj (Any): Object to calculate risk factors for (dict или объект с атрибутами).
        RiskModel (type): Django-модель RiskModel, у которой есть .objects и поля/методы:
                          - condition (str) на risk_factor
                          - get_multiplier(str) -> float

    Returns:
        dict: Dictionary with risk names as keys and calculated risk factors as values.
    """
    risks_dictionary: dict[str, float] = {}

    def has_field(o: Any, name: str) -> bool:
        if isinstance(o, Mapping):
            return name in o
        return hasattr(o, name)

    def get_field(o: Any, name: str) -> Any:
        if isinstance(o, Mapping):
            return o.get(name)
        return getattr(o, name, None)

    for risk in risks:
        base_risk: float = 1.0  # Base risk factor
        risk_factors = RiskModel.objects.filter(risk=risk)

        for risk_factor in risk_factors:
            for factor in fields:
                # быстрый фильтр по подстроке, как в исходном коде
                if factor in getattr(risk_factor, "condition", ""):
                    if has_field(obj, factor):
                        value = get_field(obj, factor)
                        if value is not None and value != "":
                            # сохраняем логику из исходника: подстановка значений строкой + eval
                            condition = str(risk_factor.condition).replace(
                                factor, str(value)
                            )
                            logger.info(
                                "Condition: %s, factor: %s, value: %s",
                                condition,
                                factor,
                                value,
                            )
                            try:
                                # намеренно оставляем eval для полной совместимости с текущими условиями
                                if eval(
                                    condition
                                ):  # noqa: S307 (осознанное использование для внутренней DSL)
                                    multiplier = risk_factor.get_multiplier(str(value))
                                    base_risk *= float(multiplier)
                            except Exception:  # глушим любые ошибки для совместимости
                                pass

        risks_dictionary[getattr(risk, "name", str(risk))] = float(base_risk)

    return risks_dictionary
