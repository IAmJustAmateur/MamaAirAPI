"""Public draft privacy notice; no authentication or consent submission."""
from django.shortcuts import render
from django.views.decorators.http import require_safe


@require_safe
def privacy_policy_page(request):
    response = render(request, "legal/privacy_policy.html")
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Cache-Control"] = "no-store"
    response["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    )
    return response
