# scripts/test_server_api.py

import requests

BASE_URL = "http://52.4.150.16/api"
API_KEY = "super-secret-mobile-key"  # from your .env
EMAIL = "testuser@example.com"
PASSWORD = "testpass123"


def log(msg):
    print(f"[✓] {msg}")


def fail(msg):
    print(f"[✗] {msg}")
    exit(1)


def post(url, data=None, headers=None):
    r = requests.post(url, json=data, headers=headers)
    return r


def get(url, headers=None):
    return requests.get(url, headers=headers)


def delete(url, headers=None):
    return requests.delete(url, headers=headers)


def login():
    r = post(f"{BASE_URL}/auth/token/", {"email": EMAIL, "password": PASSWORD})
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
    data = {"email": email, "username": "tempuser", "password": password}
    r = post(f"{BASE_URL}/auth/register/", data, headers={"X-API-Key": API_KEY})
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


if __name__ == "__main__":
    print("🔍 Running remote API test against test server...")

    test_register()
    access_token, refresh_token = login()
    test_profile(access_token)
    test_summary(access_token)
    test_set_language(access_token)
    test_logout(refresh_token, access_token)

    print("\n✅ ALL TESTS PASSED.")
