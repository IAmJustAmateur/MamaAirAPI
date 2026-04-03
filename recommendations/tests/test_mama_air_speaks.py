from django.test import TestCase
from django.utils import translation
from api.models import User
from recommendations.models import MamaAirWeeklyMessage


class MamaAirWeeklyMessageMethodTest(TestCase):

    def test_returns_message_for_user_week(self):
        user = User.objects.create_user(
            email="u@example.com", password="x", language="en"
        )
        # замокаем вычисление недели

        user.set_pregnancy_start_date()
        mamaair_msg = user.week_info()
        messageText = MamaAirWeeklyMessage.objects.get(
            week=10, locale="en", is_active=True
        ).text
        self.assertEqual(mamaair_msg["text"], messageText)
        self.assertEqual(mamaair_msg["locale"], "en")

    def test_locale_fallback_to_active_language_then_en(self):
        user = User.objects.create_user(
            email="u2@example.com", password="x", language="pl"
        )
        user.week_of_pregnancy = 10
        user.set_pregnancy_start_date()

        data = user.week_info()
        self.assertEqual(data["locale"], "en")
        self.assertEqual(data["week"], 10)

    def test_none_when_week_unknown(self):
        user = User.objects.create_user(
            email="u3@example.com", password="x", language="en"
        )
        user.week_of_pregnancy = None
        user.set_pregnancy_start_date()
        self.assertIsNone(user.week_info())
