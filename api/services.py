# api/services/advice_selector.py

from .models import AdviceTemplate


def get_current_advices(user, pregnancy_week=None):
    """
    Stub: later will filter based on user profile, pregnancy week, air exposure, etc.
    """
    return AdviceTemplate.objects.filter(is_active=True)
