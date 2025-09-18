# recommendations/tests/test_fallbacks.py
from datetime import datetime
from django.test import TestCase
from django.contrib.auth import get_user_model

from recommendations.fallbacks import build_fallback_recommendations

User = get_user_model()


def _ctx(profile=None, lifestyle=None):
    """Minimal eval context stub for fallbacks."""
    return {
        "profile": profile or {},
        "lifestyle": lifestyle or {},
        # other keys (aq, sym_m, sym_b, etc.) are not needed for fallbacks
    }


class FallbacksTests(TestCase):
    def setUp(self):
        # Minimal user (only id is used by fallbacks for deterministic tip rotation)
        self.u = User.objects.create_user(email="fb@test.com", password="x")

    def test_complete_data_when_missing(self):
        ctx = _ctx(
            profile={"week_of_pregnancy": 20},
            lifestyle={"average_sleep_hours": None, "activity_duration_minutes": None},
        )
        recs = build_fallback_recommendations(self.u, ctx)

        ids = [r["id"] for r in recs]
        self.assertIn("info.complete_data.v1", ids)

        # basic shape
        card = next(r for r in recs if r["id"] == "info.complete_data.v1")
        self.assertEqual(card["severity"], "info")
        self.assertIn("expires_at", card)

    def test_weekly_tip_by_trimester(self):
        # 2nd trimester
        ctx = _ctx(profile={"week_of_pregnancy": 22}, lifestyle={})
        recs = build_fallback_recommendations(self.u, ctx)

        # title-based match (content rotates by day, so don't match exact id)
        tips = [r for r in recs if r["title"] == "Today’s preventive tip"]
        self.assertGreaterEqual(len(tips), 1)

        tip = tips[0]
        self.assertEqual(tip["category"], "lifestyle")
        self.assertIn("expires_at", tip)
        self.assertEqual(tip["priority"], 74)

    def test_work_type_tip(self):
        ctx = _ctx(profile={"week_of_pregnancy": 15}, lifestyle={"work_type": "Desk"})
        recs = build_fallback_recommendations(self.u, ctx)

        work = [r for r in recs if r["title"] == "Workday tip"]
        self.assertEqual(len(work), 1)
        self.assertEqual(work[0]["priority"], 75)

    def test_kick_count_when_week_ge_28(self):
        ctx = _ctx(profile={"week_of_pregnancy": 30}, lifestyle={})
        recs = build_fallback_recommendations(self.u, ctx)

        ids = [r["id"] for r in recs]
        self.assertIn("info.kick_count.v1", ids)

    def test_cover_card_when_nothing_else(self):
        # No missing data, week unknown/0, no work type -> only the monitoring cover card.
        ctx = _ctx(
            profile={"week_of_pregnancy": None},
            lifestyle={"average_sleep_hours": 7.5, "activity_duration_minutes": 200},
        )
        recs = build_fallback_recommendations(self.u, ctx)

        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["id"], "info.monitoring.v1")
        self.assertEqual(recs[0]["priority"], 79)

    def test_priorities_sorted(self):
        # Trigger multiple fallbacks at once: missing data + weekly tip + work tip + kick count
        ctx = _ctx(
            profile={"week_of_pregnancy": 30},
            lifestyle={
                "average_sleep_hours": None,
                "activity_duration_minutes": None,
                "work_type": "Desk",
            },
        )
        recs = build_fallback_recommendations(self.u, ctx)
        prios = [r["priority"] for r in recs]
        self.assertEqual(prios, sorted(prios))  # ascending

    def test_expires_at_is_iso_datetime(self):
        ctx = _ctx(profile={"week_of_pregnancy": 30}, lifestyle={})
        recs = build_fallback_recommendations(self.u, ctx)
        for r in recs:
            # should be parseable ISO (with timezone offset)
            dt = datetime.fromisoformat(r["expires_at"])
            self.assertIsNotNone(dt.tzinfo)

    def test_rotation_is_stable_same_day(self):
        # The preventive tip id/message should be stable for the same user & day
        ctx = _ctx(profile={"week_of_pregnancy": 22}, lifestyle={})
        recs1 = build_fallback_recommendations(self.u, ctx)
        recs2 = build_fallback_recommendations(self.u, ctx)

        tip1 = next((r for r in recs1 if r["title"] == "Today’s preventive tip"), None)
        tip2 = next((r for r in recs2 if r["title"] == "Today’s preventive tip"), None)

        # both present and same id
        self.assertIsNotNone(tip1)
        self.assertIsNotNone(tip2)
        self.assertEqual(tip1["id"], tip2["id"])
