"""Explicit manual Gmail smoke request. Only inbox inspection proves delivery."""
import argparse
import requests

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", required=True, help="An existing active test account you control")
    args = parser.parse_args()
    response = requests.post(args.base_url.rstrip("/") + "/api/auth/password-reset/request/",
                             json={"email": args.email}, timeout=15)
    response.raise_for_status()
    print(f"API accepted request ({response.status_code}). Check your inbox/spam and worker logs; delivery is not yet verified.")
