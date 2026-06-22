# scripts/test_server_api.py

import os
import sys
import argparse
from datetime import datetime, timezone as dt_timezone
import json
import requests
from urllib.parse import urljoin
from utils import build_csv_many_points, build_json_many_points
import time
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()


ENVIRONMENTS = {
    "local": "http://127.0.0.1:8000/",
    "production": "https://api.mamaair.app/",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Run API E2E checks. Local example: "
            "python scripts/test_server_api.py --env local"
        )
    )
    parser.add_argument(
        "--env",
        choices=sorted(ENVIRONMENTS),
        default=os.getenv("E2E_ENV", "production"),
        help="Target environment. Can also be set with E2E_ENV.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("E2E_BASE_URL"),
        help="Override target base URL, for example http://127.0.0.1:8000/.",
    )
    parser.add_argument(
        "--email",
        default=os.getenv("E2E_EMAIL", "testuser003@example.com"),
        help="E2E user email. Can also be set with E2E_EMAIL.",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("E2E_PASSWORD", "testpass123"),
        help="E2E user password. Can also be set with E2E_PASSWORD.",
    )
    parser.add_argument(
        "--reg-api-key",
        default=os.getenv("REG_API_KEY", "super-secret-mobile-key"),
        help="Registration API key. Can also be set with REG_API_KEY.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.getenv("E2E_TIMEOUT", "200")),
        help="Request timeout in seconds. Can also be set with E2E_TIMEOUT.",
    )
    parser.add_argument(
        "--verify-ssl",
        choices=("true", "false"),
        default=os.getenv("E2E_VERIFY_SSL"),
        help="Verify SSL certificates. Defaults to false for local, true otherwise.",
    )
    return parser.parse_args()


ARGS = parse_args()
BASE_URL = ARGS.base_url or ENVIRONMENTS[ARGS.env]
if not BASE_URL.endswith("/"):
    BASE_URL = f"{BASE_URL}/"
API_KEY = ARGS.reg_api_key
REG_API_KEY = ARGS.reg_api_key
EMAIL = ARGS.email
PASSWORD = ARGS.password

REGISTER_URL = urljoin(BASE_URL, "api/auth/register/")

TOKEN_URL = urljoin(BASE_URL, "api/auth/token/")  # <-- изменил
REFRESH_URL = urljoin(BASE_URL, "api/auth/token/refresh/")  # <-- на будущее
PROFILE_URL = urljoin(BASE_URL, "api/profile/")
LIFESTYLE_URL = urljoin(BASE_URL, "api/lifestyle/")
CHECKLIST_URL = urljoin(BASE_URL, "api/symptoms/mommy/checklist/")

MOMMY_SELECTION_URL = urljoin(BASE_URL, "api/symptoms/mommy/selection/")
MOMMY_STATISTICS_URL = urljoin(BASE_URL, "api/symptoms/mommy/statistics/")
MOMMY_CLASS_STATISTICS_URL = urljoin(
    BASE_URL, "api/symptoms/mommy/statistics/classes/"
)

BABY_CHECKLIST_URL = urljoin(BASE_URL, "api/symptoms/baby/checklist/")
BABY_SELECTION_URL = urljoin(BASE_URL, "api/symptoms/baby/selection/")
BABY_CLASS_STATISTICS_URL = urljoin(
    BASE_URL, "api/symptoms/baby/statistics/classes/"
)

EXPOSURE_HISTORY_URL = urljoin(BASE_URL, "api/exposure/history/")

META_CHOICES_URL = urljoin(BASE_URL, "api/meta/choices/")

MOVEMENTS_UPLOAD_URL = urljoin(BASE_URL, "api/movements/upload/")
MOVEMENTS_UPLOAD_JSON_URL = urljoin(BASE_URL, "api/movements/upload/json/")
AIR_EXPOSURE_URL = urljoin(BASE_URL, "api/air-exposure/")
ADVICE_URL = urljoin(BASE_URL, "api/advice/")

DEBUG_EXPOSURE_UPSERT_URL = urljoin(BASE_URL, "api/debug/air-exposure/upsert/")

SUMMARY_URL = urljoin(BASE_URL, "api/summary/")
RECOMMENDATION_COMPLETION_URL = urljoin(BASE_URL, "api/recommendation-completion/")

WELLBEING_CATALOG_URL = urljoin(BASE_URL, "api/wellbeing/")
WELLBEING_LOG_URL = urljoin(BASE_URL, "api/wellbeing/log/")
DAILY_CHECKIN_URL = urljoin(BASE_URL, "api/daily-checkin/")
DAILY_TASKS_URL = urljoin(BASE_URL, "api/daily-tasks/")
TASK_COMPLETION_URL = urljoin(BASE_URL, "api/task-completion/")


TIMEOUT = ARGS.timeout
if ARGS.verify_ssl is None:
    VERIFY_SSL = ARGS.env != "local"
else:
    VERIFY_SSL = ARGS.verify_ssl == "true"


def pp(title, obj):
    print(f"\n== {title} ==")
    try:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    except Exception:
        print(obj)


def now_iso_with_tz():
    # ISO-8601 с локальной таймзоной машины запуска (включая оффсет)
    return datetime.now(dt_timezone.utc).astimezone().isoformat(timespec="seconds")


def date_str_from_iso(iso_dt: str) -> str:
    # берём дату в локальном времени из ISO строки
    dt = datetime.fromisoformat(iso_dt.replace("Z", "+00:00"))
    return dt.date().isoformat()


def assert_status(resp, expected, note=""):
    if isinstance(expected, (list, tuple, set)):
        ok = resp.status_code in expected
        exp_str = "/".join(map(str, expected))
    else:
        ok = resp.status_code == expected
        exp_str = str(expected)
    if not ok:
        raise AssertionError(
            f"{note} Expected {exp_str}, got {resp.status_code}: {resp.text[:500]}"
        )


def auth_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text[:500]}


def _assert_wellbeing_catalog_schema(data: dict):
    if not isinstance(data, dict):
        raise AssertionError(f"wellbeing catalog must be object, got {type(data)}")

    for k in ("water_goal", "moods", "feelings"):
        if k not in data:
            raise AssertionError(f"wellbeing catalog missing '{k}'")

    wg = data["water_goal"]
    if not isinstance(wg, dict):
        raise AssertionError("water_goal must be object")
    if "value" not in wg or "unit" not in wg:
        raise AssertionError("water_goal must have 'value' and 'unit'")

    # value может быть None (если ещё не настроено)
    if wg["value"] is not None and not isinstance(wg["value"], (int, float)):
        raise AssertionError("water_goal.value must be number or null")
    if not isinstance(wg["unit"], str) or not wg["unit"]:
        raise AssertionError("water_goal.unit must be non-empty string")
    if wg["unit"] != "ml":
        raise AssertionError(f"water_goal.unit must be 'ml', got {wg['unit']}")

    for list_name in ("moods", "feelings"):
        arr = data[list_name]
        if not isinstance(arr, list):
            raise AssertionError(f"{list_name} must be list, got {type(arr)}")
        # допускаем пустые списки, но элементы должны быть валидные
        for it in arr[:20]:
            if not isinstance(it, dict):
                raise AssertionError(f"{list_name} item must be dict")
            for k in ("id", "kind", "title", "emoji", "is_active"):
                if k not in it:
                    raise AssertionError(f"{list_name} item missing '{k}': {it}")
            if not isinstance(it["id"], int):
                raise AssertionError(f"{list_name}.id must be int")
            if not isinstance(it["title"], str):
                raise AssertionError(f"{list_name}.title must be str")
            if not isinstance(it["emoji"], str):
                raise AssertionError(f"{list_name}.emoji must be str")
            if it["kind"] not in ("mood", "feeling"):
                raise AssertionError(f"{list_name}.kind invalid: {it['kind']}")


def _pick_ids(items: list[dict], max_n: int = 2) -> list[int]:
    ids = []
    for it in items:
        if (
            isinstance(it, dict)
            and isinstance(it.get("id"), int)
            and it.get("is_active") is True
        ):
            ids.append(it["id"])
        if len(ids) >= max_n:
            break
    return ids


def _assert_wellbeing_log_schema(body: dict, expected_date: str):
    if not isinstance(body, dict):
        raise AssertionError(f"log must be object, got {type(body)}")
    for k in ("date", "water_amount", "water_unit", "moods", "feelings"):
        if k not in body:
            raise AssertionError(f"log missing '{k}'")

    if body["date"] != expected_date:
        raise AssertionError(f"log.date mismatch: {body['date']} vs {expected_date}")
    if not isinstance(body["water_amount"], (int, float)):
        raise AssertionError("water_amount must be number")
    if not isinstance(body["water_unit"], str) or not body["water_unit"]:
        raise AssertionError("water_unit must be non-empty string")
    if not isinstance(body["moods"], list) or not isinstance(body["feelings"], list):
        raise AssertionError("moods/feelings must be lists")
    for list_name in ("moods", "feelings"):
        for it in body[list_name][:20]:
            if not isinstance(it, dict):
                raise AssertionError(f"log {list_name} item must be dict")
            if "emoji" not in it:
                raise AssertionError(f"log {list_name} item missing 'emoji': {it}")
            if not isinstance(it["emoji"], str):
                raise AssertionError(f"log {list_name}.emoji must be str")


def _ids_from_items(items: list[dict]) -> list[int]:
    return sorted(x.get("id") for x in items if isinstance(x, dict))


def _assert_wellbeing_item_ids(body: dict, mood_ids=None, feeling_ids=None):
    got_mood_ids = _ids_from_items(body.get("moods", []))
    got_feel_ids = _ids_from_items(body.get("feelings", []))
    if mood_ids is not None and sorted(mood_ids) != got_mood_ids:
        raise AssertionError(f"mood ids mismatch: {got_mood_ids} vs {mood_ids}")
    if feeling_ids is not None and sorted(feeling_ids) != got_feel_ids:
        raise AssertionError(f"feeling ids mismatch: {got_feel_ids} vs {feeling_ids}")


def _assert_mommy_statistics_schema(body: list[dict]):
    if not isinstance(body, list):
        raise AssertionError(f"Mommy statistics must be list, got {type(body)}")

    for item in body[:20]:
        if not isinstance(item, dict):
            raise AssertionError(f"Mommy statistics item must be dict: {item}")
        for key in ("symptom_name", "symptom_id", "quantity", "risk_name", "risk_id"):
            if key not in item:
                raise AssertionError(f"Mommy statistics item missing '{key}': {item}")
        if not isinstance(item["symptom_name"], str):
            raise AssertionError(f"symptom_name must be str: {item}")
        if not isinstance(item["risk_name"], str):
            raise AssertionError(f"risk_name must be str: {item}")
        if not isinstance(item["symptom_id"], int):
            raise AssertionError(f"symptom_id must be int: {item}")
        if not isinstance(item["risk_id"], int):
            raise AssertionError(f"risk_id must be int: {item}")
        if not isinstance(item["quantity"], int) or item["quantity"] < 1:
            raise AssertionError(f"quantity must be positive int: {item}")


def _assert_symptom_class_statistics_schema(
    body: dict, expected_start_date: str, expected_end_date: str, expect_non_empty=False
):
    if not isinstance(body, dict):
        raise AssertionError(f"Class statistics must be object, got {type(body)}")
    for key in ("start_date", "end_date", "classes"):
        if key not in body:
            raise AssertionError(f"Class statistics missing '{key}': {body}")
    if body["start_date"] != expected_start_date:
        raise AssertionError(
            f"Class statistics start_date mismatch: {body['start_date']} vs {expected_start_date}"
        )
    if body["end_date"] != expected_end_date:
        raise AssertionError(
            f"Class statistics end_date mismatch: {body['end_date']} vs {expected_end_date}"
        )
    classes = body["classes"]
    if not isinstance(classes, list):
        raise AssertionError(f"Class statistics classes must be list, got {type(classes)}")
    if expect_non_empty and not classes:
        raise AssertionError("Class statistics classes must not be empty")

    for class_item in classes:
        if not isinstance(class_item, dict):
            raise AssertionError(f"Class statistics class item must be dict: {class_item}")
        for key in ("symptom_class", "class_name", "color_flag", "quantity", "symptoms"):
            if key not in class_item:
                raise AssertionError(
                    f"Class statistics class item missing '{key}': {class_item}"
                )
        if class_item["symptom_class"] not in (1, 2, 3, 4):
            raise AssertionError(f"Invalid symptom_class: {class_item}")
        if not isinstance(class_item["class_name"], str) or not class_item["class_name"]:
            raise AssertionError(f"class_name must be non-empty str: {class_item}")
        if not isinstance(class_item["color_flag"], str) or not class_item["color_flag"]:
            raise AssertionError(f"color_flag must be non-empty str: {class_item}")
        if not isinstance(class_item["quantity"], int) or class_item["quantity"] < 1:
            raise AssertionError(f"class quantity must be positive int: {class_item}")

        symptoms = class_item["symptoms"]
        if not isinstance(symptoms, list) or not symptoms:
            raise AssertionError(f"class symptoms must be non-empty list: {class_item}")
        for symptom in symptoms:
            if not isinstance(symptom, dict):
                raise AssertionError(f"class symptom must be dict: {symptom}")
            for key in ("symptom_name", "symptom_id", "quantity", "risks"):
                if key not in symptom:
                    raise AssertionError(f"class symptom missing '{key}': {symptom}")
            if not isinstance(symptom["symptom_name"], str):
                raise AssertionError(f"symptom_name must be str: {symptom}")
            if not isinstance(symptom["symptom_id"], int):
                raise AssertionError(f"symptom_id must be int: {symptom}")
            if not isinstance(symptom["quantity"], int) or symptom["quantity"] < 1:
                raise AssertionError(f"symptom quantity must be positive int: {symptom}")
            if not isinstance(symptom["risks"], list) or not symptom["risks"]:
                raise AssertionError(f"symptom risks must be non-empty list: {symptom}")
            for risk in symptom["risks"]:
                if not isinstance(risk, dict):
                    raise AssertionError(f"symptom risk must be dict: {risk}")
                for key in ("risk_id", "risk_name", "source_phrase"):
                    if key not in risk:
                        raise AssertionError(f"symptom risk missing '{key}': {risk}")
                if not isinstance(risk["risk_id"], int):
                    raise AssertionError(f"risk_id must be int: {risk}")
                if not isinstance(risk["risk_name"], str):
                    raise AssertionError(f"risk_name must be str: {risk}")
                if not isinstance(risk["source_phrase"], str):
                    raise AssertionError(f"source_phrase must be str: {risk}")


def _assert_summary_water_schema(
    body: dict,
    expected_date: str | None = None,
    expected_amount: float | None = None,
    expected_unit: str = "ml",
):
    water = body.get("water")
    if not isinstance(water, dict):
        raise AssertionError(f"summary.water must be object, got {type(water)}")
    for key in ("date", "amount", "unit"):
        if key not in water:
            raise AssertionError(f"summary.water missing '{key}'")
    if expected_date is not None and water["date"] != expected_date:
        raise AssertionError(f"summary.water.date mismatch: {water['date']} vs {expected_date}")
    if not isinstance(water["amount"], (int, float)):
        raise AssertionError("summary.water.amount must be number")
    if expected_amount is not None and water["amount"] != expected_amount:
        raise AssertionError(
            f"summary.water.amount mismatch: {water['amount']} vs {expected_amount}"
        )
    if water["unit"] != expected_unit:
        raise AssertionError(f"summary.water.unit mismatch: {water['unit']} vs {expected_unit}")


def _assert_daily_checkin_exists_schema(body: dict, expected_date: str):
    if not isinstance(body, dict):
        raise AssertionError(f"daily checkin response must be object, got {type(body)}")
    for k in ("date", "exists"):
        if k not in body:
            raise AssertionError(f"daily checkin response missing '{k}'")
    if body["date"] != expected_date:
        raise AssertionError(
            f"daily checkin date mismatch: {body['date']} vs {expected_date}"
        )
    if not isinstance(body["exists"], bool):
        raise AssertionError("daily checkin exists must be bool")


def _assert_daily_checkin_create_schema(body: dict, expected_date: str):
    if not isinstance(body, dict):
        raise AssertionError(
            f"daily checkin create response must be object, got {type(body)}"
        )
    for k in ("id", "date", "created_at"):
        if k not in body:
            raise AssertionError(f"daily checkin create response missing '{k}'")
    if not isinstance(body["id"], int):
        raise AssertionError("daily checkin id must be int")
    if body["date"] != expected_date:
        raise AssertionError(
            f"daily checkin create date mismatch: {body['date']} vs {expected_date}"
        )
    if not isinstance(body["created_at"], str) or not body["created_at"]:
        raise AssertionError("daily checkin created_at must be non-empty string")


def _assert_task_completion_schema(
    body: dict, expected_date: str, expected_tasks: list[str] | None = None
):
    if not isinstance(body, dict):
        raise AssertionError(f"task completion response must be object, got {type(body)}")
    for k in ("date", "tasks", "counts"):
        if k not in body:
            raise AssertionError(f"task completion response missing '{k}'")
    if body["date"] != expected_date:
        raise AssertionError(
            f"task completion date mismatch: {body['date']} vs {expected_date}"
        )
    if not isinstance(body["tasks"], list):
        raise AssertionError("task completion tasks must be list")
    for i, task in enumerate(body["tasks"]):
        if not isinstance(task, str) or not task:
            raise AssertionError(f"task completion tasks[{i}] must be non-empty string")
    if expected_tasks is not None and body["tasks"] != expected_tasks:
        raise AssertionError(
            f"task completion tasks mismatch: {body['tasks']} vs {expected_tasks}"
        )
    _assert_task_completion_counts_schema(body["counts"], "task completion counts")


def _assert_task_completion_counts_schema(counts: dict, label: str):
    if not isinstance(counts, dict):
        raise AssertionError(f"{label} must be object")
    for category in ("diet", "activity", "behavior", "mental"):
        if category not in counts:
            raise AssertionError(f"{label} missing '{category}'")
        item = counts[category]
        if not isinstance(item, dict):
            raise AssertionError(f"{label}.{category} must be object")
        for key in ("done", "total"):
            if key not in item:
                raise AssertionError(f"{label}.{category} missing '{key}'")
            if not isinstance(item[key], int) or item[key] < 0:
                raise AssertionError(f"{label}.{category}.{key} must be non-negative int")
        if item["done"] > item["total"]:
            raise AssertionError(f"{label}.{category}.done must be <= total")


def _assert_daily_tasks_schema(body: list[dict]) -> None:
    if not isinstance(body, list):
        raise AssertionError(f"daily tasks response must be list, got {type(body)}")
    if not body:
        raise AssertionError("daily tasks response must not be empty")

    previous_sort_order = None
    for i, task in enumerate(body):
        if not isinstance(task, dict):
            raise AssertionError(f"daily tasks[{i}] must be object")
        for key in ("code", "title", "category", "sort_order"):
            if key not in task:
                raise AssertionError(f"daily tasks[{i}] missing '{key}'")
        if not isinstance(task["code"], str) or not task["code"]:
            raise AssertionError(f"daily tasks[{i}].code must be non-empty string")
        if not isinstance(task["title"], str) or not task["title"]:
            raise AssertionError(f"daily tasks[{i}].title must be non-empty string")
        if task["category"] not in ("diet", "activity", "behavior", "mental"):
            raise AssertionError(
                f"daily tasks[{i}].category must be diet/activity/behavior/mental"
            )
        if not isinstance(task["sort_order"], int):
            raise AssertionError(f"daily tasks[{i}].sort_order must be int")
        if previous_sort_order is not None and task["sort_order"] < previous_sort_order:
            raise AssertionError("daily tasks must be ordered by sort_order")
        previous_sort_order = task["sort_order"]


def log(msg):
    print(f"[✓] {msg}")


def fail(msg):
    print(f"[✗] {msg}")
    exit(1)


def _assert_pollutant_compliance(pc: dict):
    if not isinstance(pc, dict):
        raise AssertionError(f"pollutant_compliance must be object, got {type(pc)}")
    for k in ("source", "version", "per_pollutant"):
        if k not in pc:
            raise AssertionError(f"pollutant_compliance missing '{k}'")

    per = pc["per_pollutant"]
    if not isinstance(per, dict):
        raise AssertionError("pollutant_compliance.per_pollutant must be object")

    # check each pollutant section for required fields if the pollutant is present
    for pol in ("pm25", "pm10"):
        if pol in per:
            item = per[pol]
            req = (
                "value",
                "unit",
                "avg_period_used",
                "value_source",
                "value_datetime",
                "limit",
                "limit_unit",
                "limit_avg_period",
                "compliance",
                "exceedance_pct",
                "approximate",
            )
            missing = [k for k in req if k not in item]
            if missing:
                raise AssertionError(f"pollutant_compliance.{pol} missing {missing}")


def _assert_today_journey_soft(obj: dict):
    # Мягкая версия: points можно не требовать (у тебя в ответе их может не быть)
    req = ("distance_m", "distance_km")
    if not isinstance(obj, dict):
        raise AssertionError(f"today_journey must be dict, got {type(obj)}")
    for k in req:
        if k not in obj:
            raise AssertionError(f"today_journey missing '{k}'")
    if not isinstance(obj["distance_m"], (int, float)):
        raise AssertionError("today_journey.distance_m must be number")
    if not isinstance(obj["distance_km"], (int, float)):
        raise AssertionError("today_journey.distance_km must be number")
    # Если points есть — слегка провалидируем
    if "points" in obj:
        if not isinstance(obj["points"], list):
            raise AssertionError("today_journey.points must be list if present")


def _assert_choice_list(arr, field_name: str):
    if not isinstance(arr, list):
        raise AssertionError(f"{field_name} must be a list, got {type(arr)}")
    if len(arr) == 0:
        raise AssertionError(f"{field_name} must not be empty")
    for item in arr:
        if not isinstance(item, dict):
            raise AssertionError(f"{field_name} items must be dicts")
        if "value" not in item or "label" not in item:
            raise AssertionError(f"{field_name} items must have 'value' and 'label'")
        if not isinstance(item["value"], str) or not isinstance(item["label"], str):
            raise AssertionError(f"{field_name} value/label must be str")
        if item["value"] == "":
            raise AssertionError(f"{field_name}.value must not be empty")


def _assert_recommendation_item(it: dict):
    # New format: alert + optional recommendation_* fields
    req = ("id", "severity", "title", "alert", "ttl_hours", "priority")
    if not isinstance(it, dict):
        raise AssertionError(f"Recommendation item must be dict, got {type(it)}")
    missing = [k for k in req if k not in it]
    if missing:
        raise AssertionError(f"Recommendation item missing keys: {missing}")
    if not isinstance(it["ttl_hours"], int):
        raise AssertionError("ttl_hours must be int")
    if not isinstance(it["priority"], int):
        raise AssertionError("priority must be int")

    # Optional fields (should be strings if present)
    for k in (
        "recommendation_diet",
        "recommendation_activity",
        "recommendation_behavior",
    ):
        if k in it and it[k] is not None and not isinstance(it[k], str):
            raise AssertionError(f"{k} must be str (or absent/null)")

    # Backward compat (optional): if server still includes 'message', ignore it


def _contains_value(arr, value: str) -> bool:
    return any(isinstance(x, dict) and x.get("value") == value for x in arr)


def step_meta_choices_public():
    """GET /meta/choices/ — публичный интеграционный тест схемы и ключевых значений."""
    r = requests.get(META_CHOICES_URL, timeout=TIMEOUT, verify=VERIFY_SSL)
    assert_status(r, 200, "Meta choices GET failed")
    data = r.json()
    pp(
        "Meta choices response (truncated)",
        {k: data.get(k, [])[:3] for k in data.keys()},
    )

    required_keys = (
        "languages",
        "races",
        "countries",
        "work_types",
        "diet_types",
        "cooking_methods",
        "exposure_levels",
    )
    for key in required_keys:
        if key not in data:
            raise AssertionError(f"Missing '{key}' in meta choices response")
        _assert_choice_list(data[key], key)

    # OPTIONAL (new) keys — validate only if backend provides them
    optional_keys = (
        "share_channels",
        "commute_modes",
        "rest_microbreak_preferences",
        "cooking_venues",
        "ventilation_levels",
    )
    for key in optional_keys:
        if key in data:
            _assert_choice_list(data[key], key)

    # anchor values (soft)
    assert _contains_value(data["languages"], "en"), "languages missing 'en'"
    assert _contains_value(data["races"], "caucasian"), "races missing 'caucasian'"
    assert _contains_value(data["countries"], "NG"), "countries missing 'NG'"
    assert _contains_value(data["work_types"], "Desk"), "work_types missing 'Desk'"
    assert _contains_value(
        data["diet_types"], "carnivore"
    ), "diet_types missing 'carnivore'"
    assert _contains_value(
        data["cooking_methods"], "gas"
    ), "cooking_methods missing 'gas'"
    assert _contains_value(
        data["exposure_levels"], "Clean"
    ), "exposure_levels missing 'Clean'"


def login_as_superuser():
    """Login as superuser from .env, return access token."""
    if ARGS.env == "local":
        email = os.getenv("LOCAL_SUPERUSER_EMAIL", "admin@example.com")
        password = os.getenv("LOCAL_SUPERUSER_PASSWORD", "admin")
    else:
        email = os.getenv("SUPERUSER_EMAIL", "admin@example.com")
        password = os.getenv("SUPERUSER_PASSWORD", "admin")

    print("Try to login as superuser:")
    print(f"email {email}, password {password}")

    payload = {"email": email, "password": password}
    r = requests.post(TOKEN_URL, data=payload, timeout=TIMEOUT, verify=VERIFY_SSL)
    assert_status(r, 200, "Superuser token obtain failed")
    data = r.json()
    access = data.get("access")
    refresh = data.get("refresh")
    if not access or not refresh:
        raise AssertionError(f"No access/refresh in token response: {data}")
    pp(
        "Superuser token response",
        {"has_access": bool(access), "has_refresh": bool(refresh)},
    )
    return access


# ---------- Existing E2E steps -------------------------------------------------


def _assert_recommendation_item(it: dict):
    req = ("id", "severity", "title", "message", "ttl_hours", "priority")
    if not isinstance(it, dict):
        raise AssertionError(f"Recommendation item must be dict, got {type(it)}")
    missing = [k for k in req if k not in it]
    if missing:
        raise AssertionError(f"Recommendation item missing keys: {missing}")
    if not isinstance(it["ttl_hours"], int):
        raise AssertionError("ttl_hours must be int")
    if not isinstance(it["priority"], int):
        raise AssertionError("priority must be int")


def _assert_today_journey(obj: dict):
    req = ("distance_m", "distance_km")
    if not isinstance(obj, dict):
        raise AssertionError(f"today_journey must be dict, got {type(obj)}")
    missing = [k for k in req if k not in obj]
    if missing:
        raise AssertionError(f"today_journey missing keys: {missing}")
    if not isinstance(obj["distance_m"], (int, float)):
        raise AssertionError("today_journey.distance_m must be number")
    if not isinstance(obj["distance_km"], (int, float)):
        raise AssertionError("today_journey.distance_km must be number")


def _assert_air_exposure_log_payload(aq: dict):
    """
    Совместимо с твоей моделью AirExposureLog: проверяем базовые поля AQ/погода/UV.
    Не требуем строго всех полей — только разумные.
    """
    if not isinstance(aq, dict):
        raise AssertionError(f"aq_weather_uv must be object, got {type(aq)}")
    # обязательные для смысла ключи (мягко)
    for k in ("timestamp", "latitude", "longitude"):
        if k not in aq:
            raise AssertionError(f"aq_weather_uv missing '{k}'")
    # типы — мягкие проверки
    for k in ("aqi", "pm25", "pm10", "temperature", "humidity", "pressure", "uvi"):
        if k in aq and aq[k] is not None and not isinstance(aq[k], (int, float)):
            raise AssertionError(f"aq_weather_uv.{k} must be number or null")


def step_summary_get(
    access_token: str,
    expected_checkin_date: str | None = None,
    expected_task_date: str | None = None,
    expected_tasks: list[str] | None = None,
    expected_water_date: str | None = None,
    expected_water_amount: float | None = None,
    expected_water_unit: str = "ml",
):
    """
    GET /api/summary/ — проверка схемы ответа согласно SummaryResponseSerializer.
    """
    r = requests.get(
        SUMMARY_URL,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Summary GET failed")
    body = safe_json(r)
    pp("Summary GET", body)

    # Верхний уровень
    for key in (
        "snapshot_id",
        "snapshot_created_at",
        "aq_weather_uv",
        "mom_exposure",
        "baby_exposure",
        "risks_delta",
        "recommendations",
        "today_journey",
        "week_info",
        "daily_exposure_level",
        "daily_checkins",
        "water",
        "task_completions",
        "exposure_history",
        "pollutant_compliance",
    ):
        if key not in body:
            raise AssertionError(f"Summary missing '{key}'")

    if not isinstance(body["snapshot_id"], int):
        raise AssertionError("snapshot_id must be int")
    if (
        not isinstance(body["snapshot_created_at"], str)
        or not body["snapshot_created_at"]
    ):
        raise AssertionError("snapshot_created_at must be non-empty string")

    # aq_weather_uv — сериализованный AirExposureLog
    _assert_air_exposure_log_payload(body["aq_weather_uv"])

    # mom_exposure — либо null, либо объект
    me = body["mom_exposure"]
    if me is not None:
        if not isinstance(me, dict):
            raise AssertionError("mom_exposure must be object or null")
        for k in ("id", "timestamp", "exposure_level", "risks"):
            if k not in me:
                raise AssertionError(f"mom_exposure missing '{k}'")
        if not isinstance(me["exposure_level"], (int, float)):
            raise AssertionError("mom_exposure.exposure_level must be number")

    # baby_exposure — либо null, либо объект (тот же формат)
    be = body["baby_exposure"]
    if be is not None:
        if not isinstance(be, dict):
            raise AssertionError("baby_exposure must be object or null")
        for k in ("id", "timestamp", "exposure_level", "risks"):
            if k not in be:
                raise AssertionError(f"baby_exposure missing '{k}'")

    # risks_delta — dict с mom/baby: number|null
    rd = body["risks_delta"]
    if not isinstance(rd, dict) or "mom" not in rd or "baby" not in rd:
        raise AssertionError("risks_delta must be an object with 'mom' and 'baby'")
    for key in ("mom", "baby"):
        if rd[key] is not None and not isinstance(rd[key], (int, float)):
            raise AssertionError(f"risks_delta.{key} must be number or null")

    # recommendations — список объектов с выбранными полями
    recs = body["recommendations"]
    if not isinstance(recs, list):
        raise AssertionError("recommendations must be a list")
    for it in recs[:5]:
        _assert_recommendation_item(it)

    # today_journey — мягкая проверка структуры
    _assert_today_journey_soft(body["today_journey"])

    # week_info — существует; тип свободный (str|dict), просто не None
    if body["week_info"] is None:
        raise AssertionError("week_info must not be null")

    # daily_exposure_level — строка или null
    if body["daily_exposure_level"] is not None and not isinstance(
        body["daily_exposure_level"], str
    ):
        raise AssertionError("daily_exposure_level must be string or null")

    daily_checkins = body["daily_checkins"]
    if not isinstance(daily_checkins, list):
        raise AssertionError("daily_checkins must be list")
    for i, item in enumerate(daily_checkins):
        if not isinstance(item, str):
            raise AssertionError(f"daily_checkins[{i}] must be string")
        _ = _parse_iso_date(item)
    if daily_checkins != sorted(daily_checkins):
        raise AssertionError(f"daily_checkins must be sorted ascending: {daily_checkins}")
    if expected_checkin_date and expected_checkin_date not in daily_checkins:
        raise AssertionError(
            f"daily_checkins must contain {expected_checkin_date}, got {daily_checkins}"
        )

    _assert_summary_water_schema(
        body,
        expected_date=expected_water_date,
        expected_amount=expected_water_amount,
        expected_unit=expected_water_unit,
    )

    # exposure_history — структура
    task_completions = body["task_completions"]
    if not isinstance(task_completions, list):
        raise AssertionError("task_completions must be list")
    task_dates = []
    for i, item in enumerate(task_completions):
        if not isinstance(item, dict):
            raise AssertionError(f"task_completions[{i}] must be object")
        for k in ("date", "tasks", "counts"):
            if k not in item:
                raise AssertionError(f"task_completions[{i}] missing '{k}'")
        if not isinstance(item["date"], str):
            raise AssertionError(f"task_completions[{i}].date must be string")
        _ = _parse_iso_date(item["date"])
        task_dates.append(item["date"])
        if not isinstance(item["tasks"], list):
            raise AssertionError(f"task_completions[{i}].tasks must be list")
        for j, task in enumerate(item["tasks"]):
            if not isinstance(task, str) or not task:
                raise AssertionError(
                    f"task_completions[{i}].tasks[{j}] must be non-empty string"
                )
        _assert_task_completion_counts_schema(
            item["counts"], f"task_completions[{i}].counts"
        )
    if task_dates != sorted(task_dates):
        raise AssertionError(
            f"task_completions must be sorted ascending: {task_dates}"
        )
    if expected_task_date:
        match = next(
            (item for item in task_completions if item["date"] == expected_task_date),
            None,
        )
        if match is None:
            raise AssertionError(
                f"task_completions must contain {expected_task_date}, got {task_completions}"
            )
        if expected_tasks is not None and match["tasks"] != expected_tasks:
            raise AssertionError(
                f"task_completions[{expected_task_date}] tasks mismatch: "
                f"{match['tasks']} vs {expected_tasks}"
            )

    hist = body["exposure_history"]
    if not isinstance(hist, dict):
        raise AssertionError("exposure_history must be object")
    for k in ("start_date", "end_date", "days_requested", "items"):
        if k not in hist:
            raise AssertionError(f"exposure_history missing '{k}'")
    if not isinstance(hist["days_requested"], int):
        raise AssertionError("exposure_history.days_requested must be int")
    if not isinstance(hist["items"], list):
        raise AssertionError("exposure_history.items must be list")
    if hist["items"]:
        first_item = hist["items"][0]
        if "date" not in first_item or "integrated_score" not in first_item:
            raise AssertionError(
                "exposure_history.items[*] must have date and integrated_score"
            )

    # pollutant_compliance — новая секция
    _assert_pollutant_compliance(body["pollutant_compliance"])


def step_1_register():
    """POST /api/auth/register/ with X-API-Key"""
    payload = {
        "email": EMAIL,
        "password": PASSWORD,
        "height": 170,
        "weight_pre_pregnancy": 65,
    }
    headers = {"X-API-Key": REG_API_KEY}
    r = requests.post(
        REGISTER_URL, json=payload, headers=headers, timeout=TIMEOUT, verify=VERIFY_SSL
    )
    # 201 — ок; если юзер уже есть, многие реализации дают 400/409 — допустим и идём дальше
    if r.status_code not in (201, 200):
        # допустим, что пользователь уже существует — тогда не падаем на 400/409
        if r.status_code not in (400, 409):
            assert_status(r, [201, 200, 400, 409], "Registration failed")
    pp("Registration response", safe_json(r))
    return r


def step_2_token():
    """POST /auth/token/ (form-encoded), returns access/refresh"""
    # сервер ожидает application/x-www-form-urlencoded, поэтому используем data=, а не json=
    # payload = {"email": EMAIL, "password": PASSWORD}
    # pp("url", TOKEN_URL)
    # r = requests.post(TOKEN_URL, payload, timeout=TIMEOUT, verify=VERIFY_SSL)
    # assert_status(r, 200, "Token obtain failed")
    # data = r.json()
    # # ожидаем ключи как в твоём login()
    # access = data.get("access")
    # refresh = data.get("refresh")
    # assert access and refresh, f"No access/refresh in token response: {data}"
    # pp("Token response", {"has_access": bool(access), "has_refresh": bool(refresh)})
    # return access
    access, refresh = login()
    return access


def step_3_fill_profile(access_token: str):
    """PATCH /api/profile/ with required/known fields"""
    payload = {
        "name": "Test User",
        "language": "en",
        "date_of_birth": "1990-01-01",
        "height": 178,
        "weight_pre_pregnancy": 70,
        "race": "caucasian",
        "country": "NG",
        "is_first_pregnancy": True,
        "week_of_pregnancy": 5,
        "tracking_enabled": True,
        "notifications_enabled": True,
        # NEW (User model + serializer mapping)
        "consent": True,
        "preferred_share_channel": "email",
    }

    r = requests.patch(
        PROFILE_URL,
        json=payload,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, [200, 202], "Profile PATCH failed")
    patched = safe_json(r)
    pp("Profile after PATCH", patched)

    # проверим GET
    r = requests.get(
        PROFILE_URL,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Profile GET failed")
    data = r.json()

    # базовые поля + новые
    for key in ("email", "language", "week_of_pregnancy", "consent"):
        assert key in data, f"Profile missing '{key}'"

    # preferred_share_channel может не вернуться, если сериалайзер ещё не задеплоен
    if "preferred_share_channel" in data:
        assert data["preferred_share_channel"] in ("email", "whatsapp", "telegram")

    # если consent=True, обычно ожидаем, что consent_accepted_at заполнится
    if data.get("consent") is True and "consent_accepted_at" in data:
        assert (
            data["consent_accepted_at"] is not None
        ), "consent_accepted_at should not be null"

    pp("Profile GET", data)


def step_3_1_put_profile_update_pregnancy_week(access_token: str):
    """PUT /api/profile/ to update week_of_pregnancy (test idempotency and PUT semantics)"""
    payload = {
        "week_of_pregnancy": 10,
        "email": EMAIL,  # PUT требует все обязательные поля, поэтому дублируем
    }

    r = requests.put(
        PROFILE_URL,
        json=payload,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, [200, 202], "Profile PUT failed")
    patched = safe_json(r)
    pp("Profile after PUT", patched)

    # проверим GET
    r = requests.get(
        PROFILE_URL,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Profile GET failed")
    data = r.json()
    assert data["week_of_pregnancy"] == 10


def step_4_lifestyle(access_token: str):
    """GET (auto-create) then PATCH /api/lifestyle/"""
    r = requests.get(
        LIFESTYLE_URL,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Lifestyle GET (autocreate) failed")
    pp("Lifestyle GET (after autocreate)", safe_json(r))

    patch_data = {
        "average_sleep_hours": 7.5,
        "work_type": "Desk",
        "diet_type": "carnivore",
        "cooking_method": "gas",
        "activity_duration_minutes": 150,
        # NEW FIELDS
        "commute_mode": "walk",
        "hydration_target_ml_per_day": 2200,
        "sleep_target_window": "22:00-06:00",
        "rest_microbreak_preference": "10min",
        "supplement_preferences": "ginger tea; moringa",
        "cooking_venue": "indoor",
        "ventilation_level": "medium",
    }

    r = requests.patch(
        LIFESTYLE_URL,
        json=patch_data,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Lifestyle PATCH failed")
    body = r.json()

    # сверка ключей
    for k, v in patch_data.items():
        if k in body:
            assert body.get(k) == v, f"Lifestyle '{k}' expected {v}, got {body.get(k)}"

    pp("Lifestyle after PATCH", body)


def step_5_check_mommy_checklist(access_token: str):
    """GET /api/symptoms/mommy/checklist/"""
    r = requests.get(
        CHECKLIST_URL,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Mommy checklist GET failed")
    data = r.json()
    pp("Mommy checklist GET", data)
    assert "symptoms" in data, f"No 'symptoms' key in checklist response: {data}"
    data = data["symptoms"]
    assert isinstance(data, list), f"Checklist should be a list, got {type(data)}"
    assert len(data) > 0, "Checklist is empty"
    # минимальная проверка структуры
    sample = data[0]
    has_id = "id" in sample
    has_name = "name" in sample
    assert has_id and has_name, f"Checklist item missing 'id'/'name': {sample}"
    pp("Mommy checklist (first 3 items)", data[:3])
    return data  # возвращаем для дальнейшего использования в тестах selection


def step_6_selection_get_today(access_token: str):
    """GET selection for 'today' (server's default date)."""
    r = requests.get(
        MOMMY_SELECTION_URL,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Selection GET (today) failed")
    body = r.json()
    assert "date" in body and "symptom_ids" in body, f"Invalid selection schema: {body}"
    assert isinstance(body["symptom_ids"], list)
    pp("Selection GET (today)", body)
    return body


def step_7_selection_post_replace(access_token: str, valid_ids: list[int]):
    """Replace-all with a concrete recorded_at, then verify by GET."""
    recorded_at_iso = now_iso_with_tz()
    expected_date = date_str_from_iso(recorded_at_iso)

    payload = {
        "recorded_at": recorded_at_iso,
        "symptom_ids": valid_ids,
    }
    r = requests.post(
        MOMMY_SELECTION_URL,
        json=payload,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Selection POST (replace) failed")
    body = r.json()
    pp("Selection POST (replace) response", body)

    # Проверки ответа
    assert body.get("recorded_at"), "Missing recorded_at in response"
    assert (
        body.get("date") == expected_date
    ), f"Unexpected 'date' in response: {body.get('date')} vs {expected_date}"
    assert sorted(body.get("symptom_ids", [])) == sorted(
        valid_ids
    ), "Mommy symptomsIDs mismatch in response"

    # Верификация GET с ?date=
    r = requests.get(
        MOMMY_SELECTION_URL,
        params={"date": expected_date},
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Selection GET by date failed")
    get_body = r.json()
    assert get_body.get("date") == expected_date
    assert sorted(get_body.get("symptom_ids", [])) == sorted(
        valid_ids
    ), "IDs mismatch on GET after POST"
    pp("Selection GET (verify after replace)", get_body)

    return expected_date


def step_7_1_mommy_statistics_get(access_token: str, target_date: str):
    """GET mommy symptom statistics by date/range and validate response schema."""
    headers = auth_headers(access_token)

    r = requests.get(
        MOMMY_STATISTICS_URL,
        params={"date": target_date},
        headers=headers,
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Mommy statistics GET by date failed")
    by_date = r.json()
    _assert_mommy_statistics_schema(by_date)
    pp("Mommy statistics GET by date", by_date)

    r = requests.get(
        MOMMY_STATISTICS_URL,
        params={"start_date": target_date, "end_date": target_date},
        headers=headers,
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Mommy statistics GET by range failed")
    by_range = r.json()
    _assert_mommy_statistics_schema(by_range)
    pp("Mommy statistics GET by range", by_range)

    r = requests.get(
        MOMMY_STATISTICS_URL,
        params={"start_date": target_date},
        headers=headers,
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 400, "Mommy statistics missing end_date should fail")
    pp("Mommy statistics GET invalid range response", safe_json(r))


def step_7_2_mommy_class_statistics_get(access_token: str, target_date: str):
    """GET mommy symptom class statistics by date/range and validate response schema."""
    headers = auth_headers(access_token)

    r = requests.get(
        MOMMY_CLASS_STATISTICS_URL,
        params={"date": target_date},
        headers=headers,
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Mommy class statistics GET by date failed")
    by_date = r.json()
    _assert_symptom_class_statistics_schema(
        by_date, target_date, target_date, expect_non_empty=True
    )
    pp("Mommy class statistics GET by date", by_date)

    r = requests.get(
        MOMMY_CLASS_STATISTICS_URL,
        params={"start_date": target_date, "end_date": target_date},
        headers=headers,
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Mommy class statistics GET by range failed")
    by_range = r.json()
    _assert_symptom_class_statistics_schema(
        by_range, target_date, target_date, expect_non_empty=True
    )
    pp("Mommy class statistics GET by range", by_range)

    r = requests.get(
        MOMMY_CLASS_STATISTICS_URL,
        params={"start_date": target_date},
        headers=headers,
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 400, "Mommy class statistics missing end_date should fail")
    pp("Mommy class statistics GET invalid range response", safe_json(r))


def step_8_selection_post_clear(access_token: str, target_date: str):
    """Send empty list to clear selection for date."""
    # Чтобы гарантировать нужную дату — укажем recorded_at на эту дату в 09:00:00+offset
    # Берём локальный offset машины
    local = datetime.now().astimezone()
    naive = datetime.fromisoformat(f"{target_date}T09:00:00")
    recorded_at = naive.replace(tzinfo=local.tzinfo).isoformat(timespec="seconds")

    payload = {"recorded_at": recorded_at, "symptom_ids": []}
    r = requests.post(
        MOMMY_SELECTION_URL,
        json=payload,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Selection POST (clear) failed")
    body = r.json()
    assert body.get("date") == target_date
    assert body.get("symptom_ids") == [], "Expected empty selection after clear"
    pp("Selection POST (clear) response", body)

    r = requests.get(
        MOMMY_SELECTION_URL,
        params={"date": target_date},
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Selection GET after clear failed")
    get_body = r.json()
    assert get_body.get("symptom_ids") == [], "GET should return empty list after clear"
    pp("Selection GET (verify after clear)", get_body)


def step_9_selection_post_invalid_ids(access_token: str):
    """Try posting invalid symptom ids, expect 400 with validation error."""
    recorded_at_iso = now_iso_with_tz()
    payload = {"recorded_at": recorded_at_iso, "symptom_ids": [999999, 888888]}
    r = requests.post(
        MOMMY_SELECTION_URL,
        json=payload,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    # Вью кидает ValidationError -> 400
    assert_status(r, 400, "Selection POST (invalid ids) should fail with 400")
    body = safe_json(r)
    pp("Selection POST (invalid ids) response", body)
    # Нестрогая проверка текста, но убедимся, что ключ присутствует
    assert "symptom_ids" in str(
        body
    ), "Response should mention 'symptom_ids' unknown ids"


def step_10_selection_get_by_date_param(access_token: str, some_date: str):
    """Explicit GET by ?date=YYYY-MM-DD must return schema and be consistent."""
    r = requests.get(
        MOMMY_SELECTION_URL,
        params={"date": some_date},
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Selection GET by date failed")
    body = r.json()
    assert body.get("date") == some_date
    assert isinstance(body.get("symptom_ids"), list)
    pp("Selection GET by date", body)


def step_11_baby_checklist(access_token: str) -> list[int]:
    """GET /symptoms/baby/checklist/ — возвращает {"symptoms": [{id,name}, ...]}"""
    r = requests.get(
        BABY_CHECKLIST_URL,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Baby checklist GET failed")
    data = r.json()
    assert isinstance(data, dict) and "symptoms" in data, f"Unexpected schema: {data}"
    items = data["symptoms"]
    assert isinstance(items, list) and len(items) > 0, "Empty baby checklist"
    # базовая валидация элемента
    sample = items[0]
    assert (
        isinstance(sample, dict) and "name" in sample and "id" in sample
    ), f"Invalid item: {sample}"
    pp("Baby checklist (first 3)", items[:3])

    # Соберём валидные ID (некоторые могут быть None по логике вью)
    valid_ids = [it["id"] for it in items if isinstance(it.get("id"), int)]
    valid_ids = list(set(valid_ids))  # уникальные
    assert len(valid_ids) > 0, "No valid baby symptom IDs in checklist"
    return valid_ids[:3]  # возьмём до 3-х


def step_12_baby_selection_get_today(access_token: str):
    r = requests.get(
        BABY_SELECTION_URL,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Baby selection GET (today) failed")
    body = r.json()
    assert (
        "date" in body
        and "symptom_ids" in body
        and isinstance(body["symptom_ids"], list)
    ), f"Invalid schema: {body}"
    pp("Baby selection GET (today)", body)
    return body


def step_13_baby_selection_post_replace(access_token: str, valid_ids: list[int]) -> str:
    print("\n--- Baby selection POST (replace) ---, step 13")
    print("Valid IDs to post:", valid_ids)
    recorded_at_iso = now_iso_with_tz()
    expected_date = date_str_from_iso(recorded_at_iso)

    payload = {"recorded_at": recorded_at_iso, "symptom_ids": valid_ids}
    r = requests.post(
        BABY_SELECTION_URL,
        json=payload,
        headers=auth_headers(access_token),
        # timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Baby selection POST (replace) failed")
    body = r.json()
    pp("Baby selection POST (replace) response", body)

    assert body.get("recorded_at"), "Missing recorded_at in response"
    assert (
        body.get("date") == expected_date
    ), f"Date mismatch: {body.get('date')} vs {expected_date}"
    assert sorted(body.get("symptom_ids", [])) == sorted(
        valid_ids
    ), "Baby symptoms IDs mismatch in response"

    # verify via GET ?date=
    r = requests.get(
        BABY_SELECTION_URL,
        params={"date": expected_date},
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Baby selection GET by date failed")
    got = r.json()
    assert got.get("date") == expected_date
    assert sorted(got.get("symptom_ids", [])) == sorted(
        valid_ids
    ), "IDs mismatch on GET after POST"
    pp("Baby selection GET (verify after replace)", got)
    return expected_date


def step_13_1_baby_class_statistics_get(access_token: str, target_date: str):
    """GET baby symptom class statistics by date/range and validate response schema."""
    headers = auth_headers(access_token)

    r = requests.get(
        BABY_CLASS_STATISTICS_URL,
        params={"date": target_date},
        headers=headers,
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Baby class statistics GET by date failed")
    by_date = r.json()
    _assert_symptom_class_statistics_schema(
        by_date, target_date, target_date, expect_non_empty=True
    )
    pp("Baby class statistics GET by date", by_date)

    r = requests.get(
        BABY_CLASS_STATISTICS_URL,
        params={"start_date": target_date, "end_date": target_date},
        headers=headers,
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Baby class statistics GET by range failed")
    by_range = r.json()
    _assert_symptom_class_statistics_schema(
        by_range, target_date, target_date, expect_non_empty=True
    )
    pp("Baby class statistics GET by range", by_range)


def step_14_baby_selection_post_clear(access_token: str, target_date: str):
    # создадим recorded_at на нужную дату в 09:00 локального TZ
    local = datetime.now().astimezone()
    naive = datetime.fromisoformat(f"{target_date}T09:00:00")
    recorded_at = naive.replace(tzinfo=local.tzinfo).isoformat(timespec="seconds")

    payload = {"recorded_at": recorded_at, "symptom_ids": []}
    r = requests.post(
        BABY_SELECTION_URL,
        json=payload,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Baby selection POST (clear) failed")
    body = r.json()
    assert (
        body.get("date") == target_date and body.get("symptom_ids") == []
    ), "Expected empty selection after clear"
    pp("Baby selection POST (clear) response", body)

    r = requests.get(
        BABY_SELECTION_URL,
        params={"date": target_date},
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Baby selection GET after clear failed")
    got = r.json()
    assert got.get("symptom_ids") == [], "GET should be empty after clear"
    pp("Baby selection GET (verify after clear)", got)


def step_15_baby_selection_post_invalid_ids(access_token: str):
    recorded_at_iso = now_iso_with_tz()
    payload = {"recorded_at": recorded_at_iso, "symptom_ids": [987654321, 876543210]}
    r = requests.post(
        BABY_SELECTION_URL,
        json=payload,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 400, "Baby selection POST (invalid ids) should return 400")
    body = safe_json(r)
    pp("Baby selection POST (invalid ids) response", body)
    assert "symptom_ids" in str(
        body
    ), "Response should mention 'symptom_ids' unknown ids"


def step_16_baby_selection_get_by_date_param(access_token: str, some_date: str):
    r = requests.get(
        BABY_SELECTION_URL,
        params={"date": some_date},
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Baby selection GET by date failed")
    body = r.json()
    assert body.get("date") == some_date and isinstance(
        body.get("symptom_ids"), list
    ), f"Invalid schema/date: {body}"
    pp("Baby selection GET by date", body)


def step_movements_upload_many(access_token: str) -> tuple[str, dict]:
    """POST /api/movements/upload с множеством точек. Возвращает (target_date, resp_body)."""
    fname, csv_bytes, target_date = build_csv_many_points()
    files = {"file": (fname, csv_bytes, "text/csv")}
    r = requests.post(
        MOVEMENTS_UPLOAD_URL,
        files=files,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    # на бэке обычно 201 (created) или 207 (multi-status, если были частичные ошибки)
    assert_status(r, [201, 207], "Movements upload failed")
    body = safe_json(r)
    pp("movements upload status code", r.status_code)
    pp("Movements upload response", body)

    # Мягкая проверка типичных ключей (если возвращаются)
    if isinstance(body, dict):
        for k in ("created", "processed", "rows_ok", "errors", "summary"):
            # допускаем отсутствие ключей: просто проверяем тип, если есть
            if k in body:
                if k in ("errors", "summary"):
                    assert isinstance(
                        body[k], (list, dict)
                    ), f"{k} must be list or dict"
                else:
                    assert (
                        isinstance(body[k], int) and body[k] >= 0
                    ), f"{k} must be non-negative int"
    return target_date, (body if isinstance(body, dict) else {})


def step_movements_upload_many_json(access_token: str) -> tuple[str, dict]:
    """POST /api/movements/upload/json с множеством точек. Возвращает (target_date, resp_body)."""
    payload, target_date = build_json_many_points()
    r = requests.post(
        MOVEMENTS_UPLOAD_JSON_URL,
        json=payload,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, [201, 207], "Movements JSON upload failed")
    body = safe_json(r)
    pp("movements JSON upload status code", r.status_code)
    pp("Movements JSON upload response", body)

    if isinstance(body, dict):
        for k in (
            "imported",
            "air_exposure_created",
            "air_exposure_updated",
            "exposures_recomputed",
            "errors",
            "exposure_errors",
        ):
            if k in body:
                if k in ("errors", "exposure_errors"):
                    assert isinstance(body[k], list), f"{k} must be a list"
                else:
                    assert (
                        isinstance(body[k], int) and body[k] >= 0
                    ), f"{k} must be non-negative int"
    return target_date, (body if isinstance(body, dict) else {})


def step_air_exposure_poll_latest(
    access_token: str, max_attempts: int = 6, delay_sec: int = 5
) -> dict:
    """
    GET /api/air-exposure/ с несколькими попытками.
    204 означает, что лог ещё не готов — подождём и повторим.
    Возвращает JSON лога при успехе (status 200).
    """
    for attempt in range(1, max_attempts + 1):
        r = requests.get(
            AIR_EXPOSURE_URL,
            headers=auth_headers(access_token),
            timeout=TIMEOUT,
            verify=VERIFY_SSL,
        )
        if r.status_code == 200:
            data = r.json()
            pp(f"AirExposureLog (attempt {attempt})", data)
            # Базовые soft-проверки схемы
            assert isinstance(
                data, dict
            ), "AirExposureLog response must be a JSON object"
            # Часто полезно наличие timestamp/id/level — проверяем мягко
            if "timestamp" in data:
                assert (
                    isinstance(data["timestamp"], str) and len(data["timestamp"]) >= 10
                ), "timestamp must be ISO-like string"
            return data
        elif r.status_code == 204:
            if attempt < max_attempts:
                time.sleep(delay_sec)
                continue
            else:
                raise AssertionError("AirExposureLog not ready after retries (204).")
        else:
            raise AssertionError(
                f"Unexpected status from /api/air-exposure/: {r.status_code} {r.text[:300]}"
            )

    raise AssertionError("AirExposureLog polling exceeded attempts.")


def step_debug_exposure_upsert(
    admin_access_token: str,
    user_email: str,
    pollutants: dict,
    timestamp_iso: str | None = None,
) -> dict:
    """
    POST /api/debug/air-exposure/upsert/
    Создаёт свежую запись Exposure для текущего пользователя с заданными агрегатами.
    Пример pollutants: {"pm25_avg_24h": 15.0}
    """
    payload = {"pollutants": pollutants, "user_email": user_email}
    if timestamp_iso:
        payload["timestamp"] = timestamp_iso

    r = requests.post(
        DEBUG_EXPOSURE_UPSERT_URL,
        json=payload,
        headers=auth_headers(admin_access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    # если эндпойнт доступен только staff — тут можно получить 403
    pp("status code", r.status_code)
    assert_status(r, [201, 200], "Debug exposure upsert failed")
    data = r.json()
    return data


def step_advice_get(access_token: str) -> dict:
    """
    GET /api/advice/
    Возвращает JSON снапшота со списком рекомендаций.
    """
    r = requests.get(
        ADVICE_URL,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Advice GET failed")
    data = r.json()
    assert "recommendations" in data and isinstance(
        data["recommendations"], list
    ), f"Bad advice schema: {data}"
    pp(
        "Advice snapshot (head)",
        {
            "created_at": data.get("created_at"),
            "count": len(data["recommendations"]),
            "first": (data["recommendations"][:1] or None),
        },
    )
    return data


def step_validate_aq_via_debug(access_token: str, min_pm25: float = 10.0):
    """
    Апсертим pm25_avg_24h >= min_pm25, затем проверяем /api/advice/, что сработал alert.pm25.daily.
    """
    # 1) апсёртим свежую экспозицию
    # now_iso = datetime.now(dt_timezone.utc).astimezone().isoformat(timespec="seconds")
    # _ = step_debug_exposure_upsert(
    #     access_token,
    #     user_email=EMAIL,
    #     pollutants={"pm25_avg_24h": max(min_pm25, 12.0)},
    #     timestamp_iso=now_iso,
    # )

    # 2) запрашиваем советы
    data = step_advice_get(access_token)
    recs = data["recommendations"]

    # 3) проверяем наличие air_quality карточки и конкретного правила
    def _has_rule(rule_id: str) -> bool:
        return any(isinstance(x, dict) and x.get("rule_id") == rule_id for x in recs)

    def _has_cat(cat: str) -> bool:
        return any(isinstance(x, dict) and x.get("category") == cat for x in recs)

    assert _has_cat(
        "air_quality"
    ), f"No 'air_quality' recommendations found: {recs[:5]}"
    assert _has_rule("alert.pm25.daily"), f"'alert.pm25.daily' not found: {recs[:5]}"

    print("✔ AQ via debug upsert validated (pm25_avg_24h >= threshold).")


def step_recommendation_completion_upsert(
    access_token: str, snapshot_id: int, rule_id: str, rule_version: int = 1
):
    payload = {
        "snapshot_id": snapshot_id,
        "rule_id": rule_id,
        "rule_version": rule_version,
        "dimension": "activity",
        "status": "done",
    }
    r = requests.post(
        RECOMMENDATION_COMPLETION_URL,
        json=payload,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, [200, 201], "Recommendation completion POST failed")
    body = safe_json(r)
    pp("Recommendation completion POST", body)

    # minimal schema checks
    for k in (
        "id",
        "snapshot_id",
        "rule_id",
        "rule_version",
        "dimension",
        "status",
        "created_at",
        "updated_at",
    ):
        if k not in body:
            raise AssertionError(f"Completion response missing '{k}'")

    if body["snapshot_id"] != snapshot_id:
        raise AssertionError("Completion snapshot_id mismatch")
    if body["rule_id"] != rule_id:
        raise AssertionError("Completion rule_id mismatch")

    return body


def step_recommendation_completion_list(access_token: str, snapshot_id: int):
    r = requests.get(
        RECOMMENDATION_COMPLETION_URL,
        params={"snapshot_id": snapshot_id},
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Recommendation completion GET failed")
    body = safe_json(r)
    pp("Recommendation completion GET", body)

    if not isinstance(body, list):
        raise AssertionError("Completion GET must return list")
    return body


def step_wellbeing_catalog(access_token: str) -> dict:
    r = requests.get(
        WELLBEING_CATALOG_URL,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Wellbeing catalog GET failed")
    data = safe_json(r)
    pp(
        "Wellbeing catalog",
        {
            "water_goal": data.get("water_goal"),
            "moods_count": len(data.get("moods", []) or []),
            "feelings_count": len(data.get("feelings", []) or []),
            "moods_head": (data.get("moods", []) or [])[:3],
            "feelings_head": (data.get("feelings", []) or [])[:3],
        },
    )
    _assert_wellbeing_catalog_schema(data)
    return data


def step_wellbeing_log_get(access_token: str, target_date: str) -> dict:
    r = requests.get(
        WELLBEING_LOG_URL,
        params={"date": target_date},
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Wellbeing log GET failed")
    body = safe_json(r)
    pp("Wellbeing log GET", body)
    _assert_wellbeing_log_schema(body, target_date)
    return body


def step_wellbeing_log_post_upsert(
    access_token: str,
    target_date: str,
    water_amount: float,
    water_unit: str,
    mood_ids: list[int] | None = None,
    feeling_ids: list[int] | None = None,
    expected_water_amount: float | None = None,
) -> dict:
    payload = {
        "date": target_date,
        "water_amount": water_amount,
        "water_unit": water_unit,
    }
    if mood_ids is not None:
        payload["mood_ids"] = mood_ids
    if feeling_ids is not None:
        payload["feeling_ids"] = feeling_ids
    r = requests.post(
        WELLBEING_LOG_URL,
        json=payload,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, [201, 200], "Wellbeing log POST (upsert) failed")
    body = safe_json(r)
    pp("Wellbeing log POST (upsert)", body)

    _assert_wellbeing_log_schema(body, target_date)
    if body["water_unit"] != water_unit:
        raise AssertionError(f"water_unit mismatch: {body['water_unit']} vs {water_unit}")
    if expected_water_amount is not None and body["water_amount"] != expected_water_amount:
        raise AssertionError(
            f"water_amount mismatch: {body['water_amount']} vs {expected_water_amount}"
        )

    # мягкая проверка, что ids применились (если сервер возвращает объекты)
    _assert_wellbeing_item_ids(body, mood_ids=mood_ids, feeling_ids=feeling_ids)

    return body


def step_daily_checkin_get(access_token: str, target_date: str) -> dict:
    r = requests.get(
        DAILY_CHECKIN_URL,
        params={"date": target_date},
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Daily checkin GET failed")
    body = safe_json(r)
    pp("Daily checkin GET", body)
    _assert_daily_checkin_exists_schema(body, target_date)
    return body


def step_daily_checkin_post_create(access_token: str, target_date: str) -> dict:
    r = requests.post(
        DAILY_CHECKIN_URL,
        json={"date": target_date},
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 201, "Daily checkin POST failed")
    body = safe_json(r)
    pp("Daily checkin POST", body)
    _assert_daily_checkin_create_schema(body, target_date)
    return body


def step_daily_checkin_ensure_exists(access_token: str, target_date: str) -> None:
    current = step_daily_checkin_get(access_token, target_date)
    if current["exists"]:
        log(f"Daily checkin already exists for {target_date}")
        return

    _ = step_daily_checkin_post_create(access_token, target_date)
    after = step_daily_checkin_get(access_token, target_date)
    if after["exists"] is not True:
        raise AssertionError("Daily checkin should exist after create")


def step_daily_tasks_get(access_token: str) -> list[dict]:
    r = requests.get(
        DAILY_TASKS_URL,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Daily tasks GET failed")
    body = safe_json(r)
    pp("Daily tasks GET", body)
    _assert_daily_tasks_schema(body)
    return body


def step_task_completion_get(access_token: str, target_date: str) -> dict:
    r = requests.get(
        TASK_COMPLETION_URL,
        params={"date": target_date},
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Task completion GET failed")
    body = safe_json(r)
    pp("Task completion GET", body)
    _assert_task_completion_schema(body, target_date)
    return body


def step_task_completion_post_replace(
    access_token: str, target_date: str, tasks: list[str]
) -> dict:
    r = requests.post(
        TASK_COMPLETION_URL,
        json={"date": target_date, "tasks": tasks},
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 201, "Task completion POST failed")
    body = safe_json(r)
    pp("Task completion POST", body)
    _assert_task_completion_schema(body, target_date, expected_tasks=tasks)
    return body


def step_task_completion_replace_and_verify(
    access_token: str, target_date: str, tasks: list[str]
) -> None:
    _ = step_task_completion_get(access_token, target_date)
    _ = step_task_completion_post_replace(access_token, target_date, tasks)
    after = step_task_completion_get(access_token, target_date)
    _assert_task_completion_schema(after, target_date, expected_tasks=tasks)


# ---------- main --------------------------------------------------------------


def post(url, data=None, headers=None):
    r = requests.post(url, json=data, headers=headers)
    return r


def get(url, headers=None):
    return requests.get(url, headers=headers)


def delete(url, headers=None):
    return requests.delete(url, headers=headers)


def login():
    # r = post(f"{BASE_URL}/auth/token/", {"email": EMAIL, "password": PASSWORD})
    r = post(TOKEN_URL, {"email": EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        fail("Login failed.")
    log("Login OK")
    return r.json()["access"], r.json()["refresh"]


def test_profile(access_token):
    r = get(f"{BASE_URL}/profile/", headers={"Authorization": f"Bearer {access_token}"})
    if r.status_code == 200:
        log("GET /profile OK")
    else:
        fail(f"GET /profile failed with status {r.status_code}")


def test_summary(access_token):
    r = get(f"{BASE_URL}/summary/", headers={"Authorization": f"Bearer {access_token}"})
    if r.status_code == 200:
        log("GET /summary OK")
    else:
        fail(f"GET /summary failed with status {r.status_code}")


def test_set_language(access_token):
    r = post(
        f"{BASE_URL}/set-language/",
        {"language": "en"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if r.status_code == 200:
        log("POST /set-language OK")
    else:
        fail(f"POST /set-language failed with status {r.status_code}")


def test_register():
    email = EMAIL
    password = PASSWORD
    data = {"email": email, "password": password}
    r = post(f"{BASE_URL}/auth/register/", data, headers={"X-API-Key": REG_API_KEY})
    if r.status_code == 201:
        log("POST /auth/register OK")
    elif r.status_code == 400:
        log("POST /auth/register: user already exists")
    else:
        fail(f"POST /auth/register failed with {r.status_code}")


def test_logout(refresh_token, access_token):
    r = post(
        f"{BASE_URL}/auth/logout/",
        {"refresh": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if r.status_code == 205:
        log("POST /logout OK")
    else:
        fail(f"POST /logout failed with {r.status_code}")


def test_upload_movements(csv_path, token):
    url = f"{BASE_URL}/movements/upload/"
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": open(csv_path, "rb")}

    response = requests.post(url, files=files, headers=headers)
    print(f"Status: {response.status_code}")
    print("Response:", response.json())
    return response


def test_upload_movements_json(data, token):
    url = f"{BASE_URL}/api/movements/upload/json/"
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.post(url, json=data, headers=headers)
    print(f"Status: {response.status_code}")
    print("Response:", response.json())
    return response


def test_upload_mommy_symptoms(data, token):
    url = f"{BASE_URL}/symptoms/mommy/checklist/"
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.post(url, json=data, headers=headers)
    print(f"Status: {response.status_code}")
    print("Response:", response.json())
    if response.status_code == 201:
        print("[✓] Mommy symptom recorded successfully")
    else:
        print("[✗] Failed to record mommy symptom")
    return response


def test_delete_account(token):
    url = f"{BASE_URL}/auth/delete-account/"
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.delete(url, headers=headers)
    print(f"Status: {response.status_code}")
    print("Response:", response.text)

    if response.status_code == 204:
        print("[✓] Account deleted")
    else:
        print("[✗] Failed to delete account")

    return response


def _parse_iso_date(s: str):
    # 'YYYY-MM-DD' -> datetime.date
    from datetime import datetime

    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        # На случай если бекенд вернёт что-то с Z/offset (не должен)
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        except Exception as e:
            raise AssertionError(f"Invalid ISO date: {s}") from e


def _assert_chronological(items: list[dict]):
    dates = [it["date"] for it in items]
    if dates != sorted(dates):
        raise AssertionError(f"Items are not chronological (asc): {dates}")


def _assert_items_schema(items: list[dict]):
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise AssertionError(f"Item #{i} must be dict, got {type(it)}")
        if "date" not in it or "integrated_score" not in it:
            raise AssertionError(f"Item #{i} missing keys: {it}")
        # date must be str and valid ISO date
        if not isinstance(it["date"], str):
            raise AssertionError(f"Item #{i}.date must be str, got {type(it['date'])}")
        _ = _parse_iso_date(it["date"])
        # score must be int/float
        if not isinstance(it["integrated_score"], (int, float)):
            raise AssertionError(
                f"Item #{i}.integrated_score must be number, got {type(it['integrated_score'])}"
            )


def _assert_items_within_window(items: list[dict], start_date, end_date):
    for it in items:
        d = _parse_iso_date(it["date"])
        if d < start_date or d > end_date:
            raise AssertionError(
                f"Date {d} out of requested window [{start_date}..{end_date}]"
            )


def step_exposure_history_default(access_token: str):
    """GET /api/exposure/history/ — default window 7 days, schema & bounds."""
    r = requests.get(
        EXPOSURE_HISTORY_URL,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Exposure history (default) failed")
    data = safe_json(r)
    pp("Exposure history (default)", data)

    # Top-level keys
    for key in ("start_date", "end_date", "days_requested", "items"):
        if key not in data:
            raise AssertionError(f"Missing '{key}' in response")

    # days_requested defaults to 7
    if data["days_requested"] != 7:
        raise AssertionError(f"days_requested expected 7, got {data['days_requested']}")

    # Dates should be valid and consistent
    start_date = _parse_iso_date(data["start_date"])
    end_date = _parse_iso_date(data["end_date"])
    if start_date > end_date:
        raise AssertionError("start_date must be <= end_date")

    items = data["items"]
    if not isinstance(items, list):
        raise AssertionError(f"'items' must be list, got {type(items)}")

    # If items present — validate schema & ordering & bounds
    if items:
        _assert_items_schema(items)
        _assert_chronological(items)
        _assert_items_within_window(items, start_date, end_date)


def step_exposure_history_days_param(access_token: str):
    """GET /api/exposure/history/?days=... — clamp & invalid handling."""
    # Case 1: days=1 -> exactly today window
    r = requests.get(
        EXPOSURE_HISTORY_URL,
        params={"days": 1},
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Exposure history days=1 failed")
    d1 = r.json()
    if d1["days_requested"] != 1:
        raise AssertionError(f"Expected days_requested=1, got {d1['days_requested']}")
    sd = _parse_iso_date(d1["start_date"])
    ed = _parse_iso_date(d1["end_date"])
    if sd != ed:
        raise AssertionError("For days=1 expected start_date==end_date")
    if d1["items"]:
        _assert_items_schema(d1["items"])
        _assert_chronological(d1["items"])
        _assert_items_within_window(d1["items"], sd, ed)
    pp("Exposure history (days=1)", d1)

    # Case 2: days=999 -> clamp to 90
    r = requests.get(
        EXPOSURE_HISTORY_URL,
        params={"days": 999},
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Exposure history days=999 failed")
    d2 = r.json()
    if d2["days_requested"] != 90:
        raise AssertionError(f"Expected clamp to 90, got {d2['days_requested']}")
    sd2 = _parse_iso_date(d2["start_date"])
    ed2 = _parse_iso_date(d2["end_date"])
    if d2["items"]:
        _assert_items_schema(d2["items"])
        _assert_chronological(d2["items"])
        _assert_items_within_window(d2["items"], sd2, ed2)
    pp("Exposure history (days=999 -> 90)", d2)

    # Case 3: days=0 -> clamp to 1
    r = requests.get(
        EXPOSURE_HISTORY_URL,
        params={"days": 0},
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Exposure history days=0 failed")
    d3 = r.json()
    if d3["days_requested"] != 1:
        raise AssertionError(f"Expected clamp to 1, got {d3['days_requested']}")
    pp("Exposure history (days=0 -> 1)", d3)

    # Case 4: days='oops' -> default 7
    r = requests.get(
        EXPOSURE_HISTORY_URL,
        params={"days": "oops"},
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Exposure history days=invalid failed")
    d4 = r.json()
    if d4["days_requested"] != 7:
        raise AssertionError(f"Expected default=7, got {d4['days_requested']}")
    pp("Exposure history (days=invalid -> 7)", d4)


def main():
    # sanity

    if REG_API_KEY == "REPLACE_ME":
        print(
            "⚠ Set REG_API_KEY env var (server's settings.REGISTRATION_API_KEY) to allow registration."
        )
        print(
            "   If user already exists, registration may still pass with 400/409 and the flow will continue.\n"
        )

    print(f"E2E_ENV: {ARGS.env}")
    print(f"BASE_URL: {BASE_URL}")
    print(f"VERIFY_SSL: {VERIFY_SSL}")
    print(f"REGISTER_URL: {REGISTER_URL}")
    print(f"TOKEN_URL: {TOKEN_URL}")
    print(f"PROFILE_URL: {PROFILE_URL}")
    print(f"LIFESTYLE_URL: {LIFESTYLE_URL}")
    print(f"CHECKLIST_URL: {CHECKLIST_URL}")
    print(f"DAILY_TASKS_URL: {DAILY_TASKS_URL}")

    # 0) Публичный эндпойнт
    step_meta_choices_public()

    step_1_register()
    token = step_2_token()
    step_3_fill_profile(token)
    step_3_1_put_profile_update_pregnancy_week(token)
    step_4_lifestyle(token)

    # --- Wellbeing (Water + Mood + Feeling) ---
    catalog = step_wellbeing_catalog(token)
    moods_ids = _pick_ids(catalog.get("moods", []), max_n=2)
    feelings_ids = _pick_ids(catalog.get("feelings", []), max_n=2)

    today = datetime.now().date().isoformat()

    # 1) GET current/default state
    initial_wellbeing_log = step_wellbeing_log_get(token, today)
    initial_water_amount = initial_wellbeing_log["water_amount"]

    # 2) POST adds water and replaces mood/feeling selections
    water_goal = catalog.get("water_goal") or {}
    unit = water_goal.get("unit") or "ml"
    if unit != "ml":
        raise AssertionError(f"Expected wellbeing water unit 'ml', got {unit}")
    first_water_add = 250
    first_wellbeing_log = step_wellbeing_log_post_upsert(
        token,
        target_date=today,
        water_amount=first_water_add,
        water_unit=unit,
        mood_ids=moods_ids,
        feeling_ids=feelings_ids,
        expected_water_amount=initial_water_amount + first_water_add,
    )

    # 3) Water-only POST must add water without clearing mood/feeling selections
    second_water_add = 125
    water_only_log = step_wellbeing_log_post_upsert(
        token,
        target_date=today,
        water_amount=second_water_add,
        water_unit=unit,
        expected_water_amount=first_wellbeing_log["water_amount"] + second_water_add,
    )
    _assert_wellbeing_item_ids(
        water_only_log, mood_ids=moods_ids, feeling_ids=feelings_ids
    )

    # 4) Verify by GET
    final_wellbeing_log = step_wellbeing_log_get(token, today)
    if final_wellbeing_log["water_amount"] != water_only_log["water_amount"]:
        raise AssertionError(
            f"Final water amount mismatch: {final_wellbeing_log['water_amount']} "
            f"vs {water_only_log['water_amount']}"
        )
    _assert_wellbeing_item_ids(
        final_wellbeing_log, mood_ids=moods_ids, feeling_ids=feelings_ids
    )
    step_daily_checkin_ensure_exists(token, today)
    daily_tasks = step_daily_tasks_get(token)
    if len(daily_tasks) < 2:
        raise AssertionError("Daily tasks catalog must have at least 2 active tasks")
    task_completion_tasks = [task["code"] for task in daily_tasks[:2]]
    step_task_completion_replace_and_verify(token, today, task_completion_tasks)
    checklist = step_5_check_mommy_checklist(token)

    # 6) GET selection for today
    step_6_selection_get_today(token)

    # подготовим валидные ID (возьмём до 3 первых)
    valid_ids = [
        item["id"] for item in checklist if isinstance(item, dict) and "id" in item
    ][:3]
    if not valid_ids:
        raise AssertionError("No valid symptom IDs from checklist to test selection")

    # 7) POST replace for a concrete recorded_at (now), then verify
    date_used = step_7_selection_post_replace(token, valid_ids)

    # 7.1) GET symptom statistics before clearing the selection
    step_7_1_mommy_statistics_get(token, date_used)
    step_7_2_mommy_class_statistics_get(token, date_used)

    # 8) clear for that date, verify empty
    step_8_selection_post_clear(token, date_used)

    # 9) invalid IDs -> 400
    step_9_selection_post_invalid_ids(token)

    # 10) GET by explicit ?date= (use today)
    today = datetime.now().date().isoformat()
    step_10_selection_get_by_date_param(token, today)

    baby_valid_ids = step_11_baby_checklist(token)  # берём валидные id из чеклиста
    pp("Baby valid IDs", baby_valid_ids)
    step_12_baby_selection_get_today(token)
    baby_date_used = step_13_baby_selection_post_replace(token, baby_valid_ids)
    step_13_1_baby_class_statistics_get(token, baby_date_used)
    step_14_baby_selection_post_clear(token, baby_date_used)
    step_15_baby_selection_post_invalid_ids(token)
    today = datetime.now().date().isoformat()
    step_16_baby_selection_get_by_date_param(token, today)

    # --- Exposure history E2E checks ---
    step_exposure_history_default(token)
    step_exposure_history_days_param(token)
    #
    # --- movements upload -> AirExposureLog ---
    target_date, upload_info = step_movements_upload_many(token)
    exposure = step_air_exposure_poll_latest(token)

    try:
        ts = exposure.get("timestamp")
        if ts:
            # лог считается свежим, если внутри последних ~12 часов
            expo_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            delta = datetime.now(dt_timezone.utc) - expo_dt.astimezone(dt_timezone.utc)
            assert (
                delta.total_seconds() < 12 * 3600
            ), f"AirExposureLog looks stale: {ts}"
    except Exception:
        pass

    print("✔ Movements uploaded and AirExposureLog generated.")

    # --- movements upload JSON -> AirExposureLog ---
    json_target_date, json_upload_info = step_movements_upload_many_json(token)
    json_exposure = step_air_exposure_poll_latest(token)

    try:
        ts = json_exposure.get("timestamp")
        if ts:
            expo_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            delta = datetime.now(dt_timezone.utc) - expo_dt.astimezone(dt_timezone.utc)
            assert (
                delta.total_seconds() < 12 * 3600
            ), f"AirExposureLog after JSON upload looks stale: {ts}"
    except Exception:
        pass

    pp("JSON movements target date", json_target_date)
    pp("JSON movements upload info", json_upload_info)
    print("✔ Movements JSON uploaded and AirExposureLog generated.")

    admin_access_token = login_as_superuser()
    # --- Advice + debug upsert -> AQ alert ---
    print("\n--- AQ via debug upsert ----")
    step_debug_exposure_upsert(
        admin_access_token, user_email=EMAIL, pollutants={"pm25_avg_24h": 20.0}
    )

    step_summary_get(
        token,
        expected_checkin_date=today,
        expected_task_date=today,
        expected_tasks=task_completion_tasks,
        expected_water_date=today,
        expected_water_amount=final_wellbeing_log["water_amount"],
        expected_water_unit=unit,
    )

    summary_r = requests.get(
        SUMMARY_URL,
        headers=auth_headers(token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(summary_r, 200, "Summary GET (for completion) failed")
    summary_body = summary_r.json()

    snapshot_id = summary_body["snapshot_id"]
    recs = summary_body.get("recommendations", [])
    rule_id = recs[0].get("rule_id") if recs else None

    # If no recs or rule_id missing, just skip completion step (soft)
    if rule_id:
        step_recommendation_completion_upsert(
            token,
            snapshot_id=snapshot_id,
            rule_id=rule_id,
            rule_version=recs[0].get("version", 1),
        )
        _ = step_recommendation_completion_list(token, snapshot_id=snapshot_id)
    else:
        print(
            "[!] No recommendations/rule_id in summary; skipping completion E2E step."
        )

    print("✔ Debug exposure upsert done, now validating advice...")
    step_validate_aq_via_debug(access_token=token, min_pm25=15.0)

    # --- Recommendation completion E2E ---
    print("\n✅ E2E flow passed.")


if __name__ == "__main__":

    try:
        main()
    except AssertionError as e:
        print(f"\n❌ Assertion failed: {e}")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"\n❌ Network error: {e}")
        sys.exit(2)
