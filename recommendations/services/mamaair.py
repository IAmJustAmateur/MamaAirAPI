# recommendations/services/mamaair.py
from django.core.cache import cache
from django.utils.translation import get_language
from recommendations.models import MamaAirMessage


def _locale_chain(locale: str):
    parts = (locale or "en").split("-")
    chain = []
    if locale:
        chain.append(locale)
    if len(parts) > 1:
        chain.append(parts[0])
    if "en" not in chain:
        chain.append("en")
    return chain


def get_mamaair_message_for_week(week: int, locale: str | None) -> dict | None:
    if not week or week < 1 or week > 40:
        return None

    for loc in _locale_chain(locale or "en"):
        cache_key = f"mamaair:{loc}:{week}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        obj = (
            MamaAirMessage.objects.filter(week=week, locale=loc, is_active=True)
            .only("text", "locale", "week", "updated_at")
            .first()
        )
        if obj:
            data = {"week": week, "locale": loc, "text": obj.text, "source": "db"}
            cache.set(cache_key, data, 3600)
            return data
    return None  # Ничего не нашли даже на en


def mamaair_speaks(user) -> dict | None:
    week = getattr(user, "current_week_of_pregnancy", lambda: None)()
    if not week:
        return None
    locale = getattr(user, "language", None) or get_language() or "en"
    return get_mamaair_message_for_week(week, locale)
