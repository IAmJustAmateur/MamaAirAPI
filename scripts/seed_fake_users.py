#!/usr/bin/env python3
import argparse
import random
import sys
from datetime import date, timedelta
from typing import Dict, Any, Optional

import requests
from faker import Faker

fake = Faker()


# ---- Adjust these if your API uses different values/choices ----
# from api.models import User, UserLifeStyle

# WORK_TYPE_CHOICES = User.WORK_TYPE_CHOICES
WORK_TYPE_CHOICES = [
    "Desk",
    "Standing",
    "Physical",
    "Care",
    "Field",
    "Domestic",
    "Night Shift",
]
# DIET_TYPE_CHOICES = UserLifeStyle.DIET_TYPE_CHOICES
DIET_TYPE_CHOICES = ["carnivore", "vegetarian"]
# COOKING_METHOD_CHOICES = UserLifeStyle.COOKING_METHOD_CHOICES
COOKING_METHOD_CHOICES = ["wood", "charcoal", "gas", "electric"]

# RACE_CHOICES = User.RACE_CHOICES
RACE_CHOICES = [
    "caucasian",
    "african",
    "asian",
    "hispanic",
    "mixed",
]
# ---------------------------------------------------------------


def build_user_payload(idx: int, email_prefix: str) -> Dict[str, Any]:
    """Return a dict matching your User create serializer."""
    name = fake.first_name()

    years = random.randint(18, 45)
    dob = date.today() - timedelta(days=years * 365 + random.randint(0, 364))

    height_cm = random.randint(150, 180)
    weight_kg = random.randint(50, 95)

    email = f"{email_prefix}{idx}@example.com".lower()
    is_first_pregnancy = random.choice([True, False])

    return {
        "email": email,  # or "username" if your API uses that
        "name": name,
        "date_of_birth": dob.isoformat(),
        "height": height_cm,
        "weight_pre_pregnancy": weight_kg,
        "race": random.choice(RACE_CHOICES),
        "password": "TestUser123!",  # remove if your endpoint doesn’t need it
        "is_first_pregnancy": is_first_pregnancy,
    }


def build_lifestyle_payload(user_id: Any) -> Dict[str, Any]:
    """Return a dict matching your UserLifeStyle create serializer."""
    return {
        "user": user_id,  # adjust if your API expects a URL instead of PK
        "average_sleep_hours": round(random.uniform(5.0, 9.5), 1),
        "work_type": random.choice(WORK_TYPE_CHOICES),
        "diet_type": random.choice(DIET_TYPE_CHOICES),
        "cooking_method": random.choice(COOKING_METHOD_CHOICES),
        "activity_duration_minutes": random.randint(0, 360),  # minutes/week
    }


def auth_headers(args: argparse.Namespace) -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if args.auth == "token":
        if not args.token:
            sys.exit("--auth token requires --token")
        # Change to "Token" or "JWT" if needed by your API
        headers["Authorization"] = f"Bearer {args.token}"
    return headers


def request_with_auth(
    method: str,
    url: str,
    headers: Dict[str, str],
    json: Optional[Dict[str, Any]] = None,
    auth: Optional[requests.auth.AuthBase] = None,
    verify_ssl: bool = True,
) -> requests.Response:
    return requests.request(
        method,
        url,
        headers=headers,
        json=json,
        auth=auth,
        timeout=30,
        verify=verify_ssl,
    )


def create_user(
    base_url: str,
    users_endpoint: str,
    headers: Dict[str, str],
    user_payload: Dict[str, Any],
    basic_auth: Optional[requests.auth.AuthBase],
    verify_ssl: bool,
) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/" + users_endpoint.lstrip("/")
    resp = request_with_auth(
        "POST", url, headers, json=user_payload, auth=basic_auth, verify_ssl=verify_ssl
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"User create failed ({resp.status_code}): {resp.text}")
    return resp.json()


def create_lifestyle(
    base_url: str,
    lifestyle_endpoint: str,
    headers: Dict[str, str],
    lifestyle_payload: Dict[str, Any],
    basic_auth: Optional[requests.auth.AuthBase],
    verify_ssl: bool,
) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/" + lifestyle_endpoint.lstrip("/")
    resp = request_with_auth(
        "POST",
        url,
        headers,
        json=lifestyle_payload,
        auth=basic_auth,
        verify_ssl=verify_ssl,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Lifestyle create failed ({resp.status_code}): {resp.text}")
    return resp.json()


def main():

    parser = argparse.ArgumentParser(description="Seed fake users + lifestyle via API")
    parser.add_argument(
        "--base-url",
        required=True,
        help="e.g. http://127.0.0.1:8000 or https://api.example.com",
        default="http://127.0.0.1:8000",
    )
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--email-prefix", default="test.mamaair.user.")
    parser.add_argument("--users-endpoint", default="/api/users/")
    parser.add_argument("--lifestyle-endpoint", default="/api/user-lifestyles/")
    parser.add_argument(
        "--verify-ssl",
        action="store_true",
        help="Turn on SSL verification (off by default for dev)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print payloads without sending requests"
    )

    # Auth
    parser.add_argument("--auth", choices=["token", "basic", "none"], default="token")
    parser.add_argument(
        "--token",
        help="Bearer token for --auth token",
        default="dev_default_token_12345",
    )
    parser.add_argument("--username", help="Username/email for --auth basic")
    parser.add_argument("--password", help="Password for --auth basic")

    args = parser.parse_args()

    headers = auth_headers(args)
    basic_auth = None
    if args.auth == "basic":
        if not (args.username and args.password):
            sys.exit("--auth basic requires --username and --password")
        basic_auth = requests.auth.HTTPBasicAuth(args.username, args.password)

    success_users = 0
    success_lifestyles = 0
    failures = []

    for i in range(args.start_index, args.start_index + args.count):
        user_payload = build_user_payload(i, args.email_prefix)
        if args.dry_run:
            print("[DRY RUN] Would create user:", user_payload)
            created_user = {"id": i}
        else:
            try:
                created_user = create_user(
                    args.base_url,
                    args.users_endpoint,
                    headers,
                    user_payload,
                    basic_auth,
                    args.verify_ssl,
                )
                success_users += 1
            except Exception as e:
                failures.append(f"User {user_payload.get('email')}: {e}")
                continue

        user_id = created_user.get("id") or created_user.get("pk")
        if user_id is None:
            failures.append(
                f"Lifestyle for {user_payload.get('email')}: missing user id in response"
            )
            continue

        lifestyle_payload = build_lifestyle_payload(user_id)

        if args.dry_run:
            print("[DRY RUN] Would create lifestyle:", lifestyle_payload)
            success_lifestyles += 1
        else:
            try:
                create_lifestyle(
                    args.base_url,
                    args.lifestyle_endpoint,
                    headers,
                    lifestyle_payload,
                    basic_auth,
                    args.verify_ssl,
                )
                success_lifestyles += 1
            except Exception as e:
                # If OneToOne already exists, your API might return 400/409; log and continue
                failures.append(f"Lifestyle for {user_payload.get('email')}: {e}")
                continue

    print("\n=== Summary ===")
    print(f" Users created:      {success_users}")
    print(f" Lifestyles created: {success_lifestyles}")
    if failures:
        print(" Failures:")
        for f in failures:
            print("  -", f)


if __name__ == "__main__":
    main()
