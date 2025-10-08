from django.test import TestCase
from django.utils import translation
from api.models import User
from recommendations.models import MamaAirMessage


class MamaAirSpeaksMethodTest(TestCase):

    def test_returns_message_for_user_week(self):
        user = User.objects.create_user(
            email="u@example.com", password="x", language="en"
        )
        # замокаем вычисление недели
        user.week_of_pregnancy = 10
        user.save()
        mamaair_msg = user.mamaair_speaks()
        messageText = MamaAirMessage.objects.get(
            week=10, locale="en", is_active=True
        ).text
        self.assertEqual(mamaair_msg["text"], messageText)
        self.assertEqual(mamaair_msg["locale"], "en")

    def test_locale_fallback_to_active_language_then_en(self):
        user = User.objects.create_user(
            email="u2@example.com", password="x", language="pl"
        )
        user.week_of_pregnancy = 10
        user.save()

        data = user.mamaair_speaks()
        self.assertEqual(data["locale"], "en")
        self.assertEqual(data["week"], 10)

    def test_none_when_week_unknown(self):
        user = User.objects.create_user(
            email="u3@example.com", password="x", language="en"
        )
        user.week_of_pregnancy = None
        user.save()
        self.assertIsNone(user.mamaair_speaks())
