from django.db import models

from django.db.models import Q, UniqueConstraint


class RecommendationRuleQuerySet(models.QuerySet):
    def active(self):
        return self.filter(enabled=True).order_by("priority", "-updated_at")


# RecommendationRule fields (MVP engine):
#
# - rule_id (str) + version (int)
#     Стабильный идентификатор и версия правила. Позволяют обновлять логику без потери истории.
#
# - condition (str)
#     Python-выражение, которое исполняется через eval в песочнице.
#     Доступные переменные и хелперы приходят из EvalContextBuilder:
#       profile, lifestyle, aq, sym_m, sym_b, is_20w_plus,
#       m(name), b(name), count_m(...), count_b(...),
#       poll(key), ge_poll(key, threshold),
#       exists(x), ge(a, b), le(a, b), count_true(...), any_of(...), all_of(...), now().
#     Должно вернуть True/False.
#
# - severity (enum: critical | high | moderate | info)
#     Влияет на приоритет и UX (цвет/иконки).
#
# - priority (int, "меньше = важнее")
#     Единая шкала ранжирования карточек. Рекомендуемая сетка:
#       0–9   : критические медицинские (неотложные)
#       10–29 : высокий риск (важно, но не экстренно)
#       30–49 : средний приоритет (в т.ч. AQ-алерты)
#       50–69 : лайфстайл/профиль (поведенческие советы)
#       70+   : информационные / nice-to-have
#     Внутри диапазона использовать шаг 1–2 как тай-брейкер (срочность, специфичность, конкретика действия).
#
# - cooldown_hours (int)
#     Минимальный интервал между ПОВТОРНЫМИ срабатываниями одного и того же правила для одного пользователя.
#     Помогает не "спамить". Примеры дефолтов:
#       critical: 24–48ч, high: 24ч, AQ: 12ч, lifestyle/profile: 7дней (168ч).
#
# - ttl_hours (int)
#     "Время жизни" рекомендации — сколько она считается актуальной/видимой после генерации снапшота.
#     Примеры: critical/high: 24ч; AQ: 12–24ч; lifestyle/profile: 7дней.
#
# - category (enum: medical | air_quality | lifestyle | general)
#     Для группировки/фильтров в UI.
#
# - enabled (bool)
#     Флаг включения правила (для быстрых откатов/тестов).


class RecommendationRule(models.Model):
    """
    Простая модель правила для eval-движка.
    condition — это Python-выражение, которое получает контекст из EvalContextBuilder и
    ДОЛЖНО вернуть True/False.
    """

    SEVERITY_CHOICES = [
        ("critical", "Critical"),
        ("high", "High"),
        ("moderate", "Moderate"),
        ("info", "Info"),
    ]
    CATEGORY_CHOICES = [
        ("medical", "Medical"),
        ("air_quality", "Air Quality"),
        ("lifestyle", "Lifestyle"),
        ("general", "General"),
    ]

    # Идентификация/версионирование
    rule_id = models.CharField(max_length=128)  # например: "alert.pm25.daily"
    version = models.PositiveIntegerField(default=1)

    # Контент
    title = models.CharField(max_length=255)
    condition = models.TextField(
        help_text="Python expression, returns True/False against eval context."
    )
    alert = models.TextField()
    recommendation_diet = models.TextField(blank=True, default="")
    recommendation_activity = models.TextField(blank=True, default="")
    recommendation_behavior = models.TextField(blank=True, default="")

    # Метаданные
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

    # Служебные поля
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
    week = models.PositiveSmallIntegerField()  # 1..40
    locale = models.CharField(max_length=10, default="en")  # "en", "en-US", "ru"
    text = models.TextField()
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)  # для вашего контроля
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
