# api/services/user_risks.py
from typing import Any, Iterable, Mapping, Sequence

# Safe to import: this module doesn't import your models
from api.services.risks_engine import calculate_risks


def select_risk_fields(
    obj: Any,
    explicit_fields: Sequence[str] | None = None,
) -> list[str]:
    """
    Field selection strategy:
      1) If explicit_fields passed — use them.
      2) If the object defines get_risk_fields() — use it.
      3) If the class has RISK_FIELDS (iterable or callable) — use it.
      4) If obj is a Mapping (dict-like) — use keys().
      5) Otherwise — empty list (no magic introspection).
    """
    if explicit_fields is not None:
        return list(explicit_fields)

    get_rf = getattr(obj, "get_risk_fields", None)
    if callable(get_rf):
        return list(get_rf())

    class_rf = getattr(obj.__class__, "RISK_FIELDS", None)
    if class_rf is not None:
        return list(class_rf() if callable(class_rf) else class_rf)

    if isinstance(obj, Mapping):
        return list(obj.keys())

    return []


def compute_risks(
    *,
    obj: Any,
    RiskModel: type,
    risks_qs: Iterable[Any],
    fields: Sequence[str] | None = None,
) -> dict[str, float]:
    """
    Thin wrapper over risk_engine.calculate_risks that prepares field names.
    """
    field_names = select_risk_fields(obj, fields)
    return calculate_risks(
        risks=risks_qs,
        fields=field_names,
        obj=obj,
        RiskModel=RiskModel,
    )
