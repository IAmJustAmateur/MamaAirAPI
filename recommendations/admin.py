from django.contrib import admin
from django import forms
from django.utils.safestring import mark_safe
from .models import RecommendationRule, MamaAirMessage

CHEATSHEET_HTML = """
<details open>
  <summary><strong>RecommendationRule — cheat sheet</strong></summary>
  <ul>
    <li><b>condition</b> — a Python expression evaluated in a sandbox. Available:
      <code>profile</code>, <code>lifestyle</code>, <code>aq</code>,
      <code>sym_m</code> (mom), <code>sym_b</code> (baby), <code>is_20w_plus</code>;
      helpers: <code>m(name)</code>, <code>b(name)</code>, <code>count_m(...)</code>, <code>count_b(...)</code>,
      <code>poll(key)</code>, <code>ge_poll(key, threshold)</code>,
      <code>exists(x)</code>, <code>ge(a,b)</code>, <code>le(a,b)</code>,
      <code>count_true(...)</code>, <code>any_of(...)</code>, <code>all_of(...)</code>.
    </li>
    <li><b>priority</b> (lower = more important):
      0–9 critical, 10–29 high, 30–49 moderate (incl. AQ), 50–69 lifestyle/profile, 70+ info.
      Use small steps (1–2) inside a band to break ties by urgency/specificity/actionability.
    </li>
    <li><b>cooldown_hours</b> — minimum interval between repeat firings of the SAME rule for the SAME user
      (e.g., critical: 24–48h; AQ: 12h; lifestyle/profile: 7 days).
    </li>
    <li><b>ttl_hours</b> — how long a card is considered “fresh/visible” after snapshot generation
      (critical/high: 24h; AQ: 12–24h; lifestyle/profile: 7 days).
    </li>
  </ul>
  <p><b>Examples:</b></p>
  <pre style="white-space:pre-wrap">ge_poll('pm25_avg_24h', 10)
count_true(is_20w_plus, m('high blood pressure'), m('headache')) >= 3
lifestyle.get('cooking_method') in ('wood','charcoal')</pre>
</details>
"""


class RecommendationRuleForm(forms.ModelForm):
    class Meta:
        model = RecommendationRule
        fields = "__all__"
        help_texts = {
            "condition": "Python expression evaluated in a sandbox. See the cheat sheet above.",
            "priority": "Lower = more important. See the priority bands in the cheat sheet.",
            "cooldown_hours": "Minimum interval between repeated firings of this rule for a user.",
            "ttl_hours": "How long the card stays fresh/visible after snapshot generation.",
        }


@admin.register(RecommendationRule)
class RecommendationRuleAdmin(admin.ModelAdmin):
    form = RecommendationRuleForm

    list_display = (
        "rule_id",
        "version",
        "enabled",
        "severity",
        "category",
        "priority",
        "updated_at",
    )
    list_filter = ("enabled", "severity", "category")
    search_fields = ("rule_id", "title", "condition", "message")
    ordering = ("priority", "-updated_at")

    # Show a cheat sheet at the top of the add/change form
    fieldsets = (
        ("Cheat sheet", {"fields": tuple(), "description": mark_safe(CHEATSHEET_HTML)}),
        (
            "Identification",
            {
                "fields": (
                    "rule_id",
                    "version",
                    "enabled",
                    "category",
                    "severity",
                    "priority",
                )
            },
        ),
        ("Logic", {"fields": ("condition",)}),
        ("Content", {"fields": ("title", "message")}),
        ("Delivery", {"fields": ("cooldown_hours", "ttl_hours")}),
    )

    # Also show the cheat sheet on the changelist page
    change_list_template = "admin/recommendations/recommendationrule/change_list.html"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["cheatsheet_html"] = mark_safe(CHEATSHEET_HTML)
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(MamaAirMessage)
class MamaAirMessageAdmin(admin.ModelAdmin):
    list_display = ("week", "locale", "is_active", "version", "updated_at")
    list_filter = ("locale", "is_active")
    search_fields = ("text",)
    list_editable = ("is_active",)
