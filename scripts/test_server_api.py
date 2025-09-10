# scripts/test_server_api.py

import os
import sys
from datetime import datetime, timedelta, timezone as dt_timezone
import json
import requests
from urllib.parse import urljoin

BASE_URL = "http://52.4.150.16/"
# BASE_URL = "http://127.0.0.1:8000/"
# API_KEY = "super-secret-mobile-key"  # from your .env
REG_API_KEY = "super-secret-mobile-key"  # from your .env
EMAIL = "testuser32@example.com"
PASSWORD = "testpass123"

# BASE_URL_RAW = os.getenv("BASE_URL", "http://52.4.150.16/")
# BASE_URL_RAW = os.getenv("BASE_URL", "http://127.0.0.1:8000/")
# BASE_URL = BASE_URL_RAW.rstrip("/") + "/"

REGISTER_URL = urljoin(BASE_URL, "api/auth/register/")
TOKEN_URL = urljoin(BASE_URL, "api/auth/token/")  # <-- изменил
REFRESH_URL = urljoin(BASE_URL, "api/auth/token/refresh/")  # <-- на будущее
PROFILE_URL = urljoin(BASE_URL, "api/profile/")
LIFESTYLE_URL = urljoin(BASE_URL, "api/lifestyle/")
CHECKLIST_URL = urljoin(BASE_URL, "api/symptoms/mommy/checklist/")

MOMMY_SELECTION_URL = urljoin(BASE_URL, "api/symptoms/mommy/selection/")

META_CHOICES_URL = urljoin(BASE_URL, "api/meta/choices/")

TIMEOUT = 20
VERIFY_SSL = True  # http у тебя сейчас — флаг игнорируется


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


def log(msg):
    print(f"[✓] {msg}")


def fail(msg):
    print(f"[✗] {msg}")
    exit(1)


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

    # Якорные значения из твоего примера (мягкие проверки)
    assert _contains_value(data["languages"], "en"), "languages missing 'en'"
    assert _contains_value(data["races"], "caucasian"), "races missing 'caucasian'"
    assert _contains_value(data["countries"], "nigeria"), "countries missing 'nigeria'"
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


# ---------- Existing E2E steps -------------------------------------------------


def step_1_register():
    """POST /api/auth/register/ with X-API-Key"""
    payload = {"email": EMAIL, "password": PASSWORD}
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
    # подставляю реалистичные значения под твою ожидаемую схему
    payload = {
        "name": "Test User",
        "language": "en",
        "date_of_birth": "1990-01-01",
        "height": 178,
        "weight_pre_pregnancy": 70,
        "race": "caucasian",
        "country": "nigeria",
        "is_first_pregnancy": True,
        "week_of_pregnancy": 12,
        "tracking_enabled": True,
        "notifications_enabled": True,
    }
    r = requests.patch(
        PROFILE_URL,
        json=payload,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, [200, 202], "Profile PATCH failed")
    pp("Profile after PATCH", safe_json(r))

    # проверим GET
    r = requests.get(
        PROFILE_URL,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Profile GET failed")
    data = r.json()
    # базовые поля, которые ты ожидал в примере
    for key in ("email", "language", "week_of_pregnancy"):
        assert key in data, f"Profile missing '{key}'"
    pp("Profile GET", data)


def step_4_lifestyle(access_token: str):
    """GET (auto-create) then PATCH /api/lifestyle/"""
    # 1) GET — у тебя в тестах он автосоздаёт строку, если её нет
    r = requests.get(
        LIFESTYLE_URL,
        headers=auth_headers(access_token),
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    assert_status(r, 200, "Lifestyle GET (autocreate) failed")
    pp("Lifestyle GET (after autocreate)", safe_json(r))

    # 2) PATCH — обновим значения под тесты
    patch_data = {
        "average_sleep_hours": 7.5,
        "work_type": "Desk",
        "diet_type": "carnivore",
        "cooking_method": "gas",
        "activity_duration_minutes": 150,
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
    # быстрая сверка ключей
    for k, v in patch_data.items():
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
    ), f"IDs mismatch in response"

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
    url = f"{BASE_URL}/movements/upload"
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": open(csv_path, "rb")}

    response = requests.post(url, files=files, headers=headers)
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


def main():
    # sanity
    if REG_API_KEY == "REPLACE_ME":
        print(
            "⚠ Set REG_API_KEY env var (server's settings.REGISTRATION_API_KEY) to allow registration."
        )
        print(
            "   If user already exists, registration may still pass with 400/409 and the flow will continue.\n"
        )

    print(f"BASE_URL: {BASE_URL}")
    print(f"REGISTER_URL: {REGISTER_URL}")
    print(f"TOKEN_URL: {TOKEN_URL}")
    print(f"PROFILE_URL: {PROFILE_URL}")
    print(f"LIFESTYLE_URL: {LIFESTYLE_URL}")
    print(f"CHECKLIST_URL: {CHECKLIST_URL}")

    # 0) Публичный эндпойнт
    step_meta_choices_public()

    step_1_register()
    token = step_2_token()
    step_3_fill_profile(token)
    step_4_lifestyle(token)
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

    # 8) clear for that date, verify empty
    step_8_selection_post_clear(token, date_used)

    # 9) invalid IDs -> 400
    step_9_selection_post_invalid_ids(token)

    # 10) GET by explicit ?date= (use today)
    today = datetime.now().date().isoformat()
    step_10_selection_get_by_date_param(token, today)

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
    # print("🔍 Running remote API test against test server...")

    # test_register()
    # access_token, refresh_token = login()

    # test_profile(access_token)
    # test_summary(access_token)
    # test_set_language(access_token)

    # print("\n✅ Uploading valid CSV:")
    # test_upload_movements("test_data/valid_movements.csv", access_token)

    # payload = {
    #     "symptom": "Headache",
    #     "user": 1,  # Assuming user ID 1 exists
    #     "severity": 3,
    #     "date_recorded": "2025-07-18",
    # }
    # print("\n✅ Uploading valid mommy symptom:")
    # test_upload_mommy_symptoms(payload, access_token)

    # print("\n⚠️ Uploading invalid CSV:")
    # test_upload_movements("test_data/invalid_movements.csv", access_token)

    # test_logout(refresh_token, access_token)

    # print("\n🗑️ Deleting user account:")
    # test_delete_account(access_token)

    # print("\n✅ ALL TESTS PASSED.")
