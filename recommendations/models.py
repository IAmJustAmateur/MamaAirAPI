from typing import ClassVar

from django.db import models
from django.db.models import Q, UniqueConstraint


class RecommendationRuleQuerySet(models.QuerySet):
    def active(self):
        return self.filter(enabled=True).order_by("priority", "-updated_at")


# RecommendationRule fields (MVP engine):
#
# - rule_id (str) + version (int)
#     Stable rule identifier and version. A new version can change rule logic while
#     preserving references stored in existing snapshots and completion records.
#
# - condition (str)
#     A Python expression evaluated with empty built-ins and a context supplied by
#     EvalContextBuilder. Available data and helpers include:
#       profile, lifestyle, aq, wellbeing, sym_m, sym_b, is_20w_plus,
#       m(name), b(name), count_m(...), count_b(...),
#       mood(code), feeling(code),
#       poll(key), ge_poll(key, threshold),
#       exists(x), ge(a, b), le(a, b), count_true(...), any_of(...), all_of(...), now().
#     The expression must produce a truthy or falsy value. Evaluation errors are
#     treated as a non-match by the current evaluator.
#
# - alert and recommendation_* (str)
#     User-facing card content. Recommendation dimensions currently supported by
#     snapshots and Daily Plan are diet, activity, behavior, and mental wellbeing.
#
# - severity (enum: critical | high | moderate | info)
#     Urgency metadata exposed to API clients. It may drive client presentation,
#     but it does not affect server-side ordering by itself.
#
# - priority (int, lower = more important)
#     The explicit server-side ordering value. Recommended bands:
#       0-9   : critical medical alerts
#       10-29 : high risk, important but not immediately urgent
#       30-49 : moderate priority, including air-quality alerts
#       50-69 : lifestyle, profile, and wellbeing guidance
#       70+   : informational or nice-to-have content
#     Within a band, use increments of 1-2 to break ties by urgency, specificity,
#     and actionability.
#
# - cooldown_hours (int)
#     Reserved delivery-policy metadata. The current evaluator does not enforce a
#     per-user cooldown, so matching rules may appear in every newly generated
#     snapshot regardless of this value.
#
# - ttl_hours (int)
#     Used when a snapshot is generated to calculate the card's expires_at value.
#     Snapshot reuse is controlled separately by the configured freshness window;
#     the server does not currently remove expired cards from stored snapshots.
#
# - category (enum: medical | air_quality | lifestyle | general)
#     Classification metadata for clients and admin filtering. Daily Plan also maps
#     medical recommendation actions to the service/support group.
#
# - enabled (bool)
#     Controls whether the evaluator includes the rule in its active queryset.
class RecommendationRule(models.Model):
    """
    Database-backed rule used by the MVP recommendation evaluator.

    ``condition`` is a Python expression evaluated against the context produced by
    ``EvalContextBuilder``. It must produce a truthy or falsy value.
    """

    SEVERITY_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("critical", "Critical"),
        ("high", "High"),
        ("moderate", "Moderate"),
        ("info", "Info"),
    )
    CATEGORY_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("medical", "Medical"),
        ("air_quality", "Air Quality"),
        ("lifestyle", "Lifestyle"),
        ("general", "General"),
    ]

    # Identification and versioning
    rule_id = models.CharField(max_length=128)  # Example: "alert.pm25.daily"
    version = models.PositiveIntegerField(default=1)

    # User-facing content and matching condition
    title = models.CharField(max_length=255)
    condition = models.TextField(
        help_text="Python expression, returns True/False against eval context."
    )
    alert = models.TextField()
    recommendation_diet = models.TextField(blank=True, default="")
    recommendation_activity = models.TextField(blank=True, default="")
    recommendation_behavior = models.TextField(blank=True, default="")
    recommendation_mental = models.TextField(blank=True, default="")

    # Classification and delivery metadata
    severity = models.CharField(max_length=16, choices=SEVERITY_CHOICES, default="info")
    category = models.CharField(
        max_length=32, choices=CATEGORY_CHOICES, default="general"
    )
    enabled = models.BooleanField(default=True)
    priority = models.IntegerField(
        default=100, help_text="Lower number = higher priority."
    )
    cooldown_hours = models.PositiveIntegerField(default=24)
    ttl_hours = models.PositiveIntegerField(default=24)

    # Audit timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = RecommendationRuleQuerySet.as_manager()

    class Meta:
        db_table = "recommendation_rules"
        ordering = ["priority", "-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["rule_id", "version"], name="uniq_rule_id_version"
            )
        ]
        indexes = [
            models.Index(fields=["enabled", "priority"]),
            models.Index(fields=["category"]),
        ]

    def __str__(self):
        return f"{self.rule_id}.v{self.version} ({'on' if self.enabled else 'off'})"


class MamaAirWeeklyMessage(models.Model):
    week = models.PositiveSmallIntegerField()  # Pregnancy week, normally 1-40
    locale = models.CharField(max_length=10, default="en")  # Examples: "en", "en-US"
    text = models.TextField()
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)  # Content revision number
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["week", "locale"],
                condition=Q(is_active=True),
                name="unique_active_mamaair_week_locale",
            )
        ]
        indexes = [
            models.Index(fields=["week", "locale", "is_active"]),
        ]

    def __str__(self):
        return f"{self.locale} / week {self.week} (active={self.is_active})"
