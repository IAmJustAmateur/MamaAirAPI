from django.db import migrations


RULES = [
    {
        "rule_id": "alert.placental_abruption",
        "version": 1,
        "title": "Possible placental abruption",
        "condition": (
            "count_true("
            "m('vaginal bleeding'), "
            "m('abdominal pain'), "
            "m('severe abdominal pain'), "
            "m('lower back pain'), "
            "m('contractions'), "
            "m('uterine tenderness'), "
            "m('uterine rigidity')"
            ") >= 3"
        ),
        "alert": "Call emergency services / go to hospital immediately for bleeding with pain, tenderness, or frequent contractions.",
        "recommendation_diet": "Do not delay urgent care to eat or drink; follow hospital instructions once you are being assessed.",
        "recommendation_activity": "Stop what you are doing and get medical help now. Do not drive yourself; arrange emergency transport or go to the hospital/maternity unit.",
        "recommendation_behavior": "Avoid heavy physical lifting or high-stress tasks, especially during extreme heat, until you have been assessed.",
        "severity": "critical",
        "category": "medical",
        "enabled": True,
        "priority": 5,
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    {
        "rule_id": "alert.preeclampsia",
        "version": 1,
        "title": "Possible preeclampsia",
        "condition": (
            "is_20w_plus and count_true("
            "m('high blood pressure'), "
            "m('headache'), "
            "m('persistent headache'), "
            "m('upper abdominal pain'), "
            "m('blurred vision'), "
            "m('severe swelling of the face or hands'), "
            "b('reduced fetal movement')"
            ") >= 3"
        ),
        "alert": "Contact your OB/GYN today; these can be warning signs of preeclampsia. If symptoms are severe, seek urgent care.",
        "recommendation_diet": "Keep your standard prenatal diet and take clinician-prescribed calcium/iron-folate supplements as advised. Include calcium-rich foods such as small fish eaten with bones and dark leafy greens.",
        "recommendation_activity": "Avoid strenuous exercise until you have been evaluated. Stay hydrated, keep cool, and avoid overheating.",
        "recommendation_behavior": "If you have severe headache, vision changes, severe swelling, upper abdominal pain, or reduced fetal movement, seek urgent assessment.",
        "severity": "critical",
        "category": "medical",
        "enabled": True,
        "priority": 6,
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    {
        "rule_id": "alert.preterm_labor",
        "version": 1,
        "title": "Signs of preterm labor",
        "condition": (
            "count_true("
            "m('contraction frequency'), "
            "m('increased heart rate'), "
            "m('non-specific abdominal pain'), "
            "m('non-specific back pain'), "
            "m('fever'), "
            "m('vaginal bleeding'), "
            "b('reduced fetal movement')"
            ") >= 3"
        ),
        "alert": "Call your maternity doctor; these may be signs of preterm labor.",
        "recommendation_diet": "Keep your usual prenatal diet and stay well-hydrated. During severe heat, use frequent small sips of clean water and light broths or porridge.",
        "recommendation_activity": "Do not start bed rest on your own. Stop strenuous work, rest in a shaded well-ventilated room, and contact your doctor first.",
        "recommendation_behavior": "Strictly avoid oral neem leaf tea or neem-infused remedies in pregnancy. Get urgent assessment if you have contractions, bleeding, leaking fluid, fever, or reduced fetal movement.",
        "severity": "critical",
        "category": "medical",
        "enabled": True,
        "priority": 7,
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    {
        "rule_id": "alert.prom",
        "version": 1,
        "title": "Possible leaking fluid",
        "condition": "m('leaking fluid')",
        "alert": "Contact your maternity unit urgently; leaking fluid may indicate premature rupture of membranes.",
        "recommendation_diet": "Keep hydrated with clean water while arranging care, unless a clinician tells you otherwise.",
        "recommendation_activity": "Avoid strenuous activity and do not insert anything vaginally. Go for assessment as soon as possible.",
        "recommendation_behavior": "Note the time, color, smell, and amount of fluid and report it to the maternity team.",
        "severity": "critical",
        "category": "medical",
        "enabled": True,
        "priority": 8,
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    {
        "rule_id": "alert.fetal_hypoxia",
        "version": 1,
        "title": "Reduced fetal movement pattern",
        "condition": (
            "any_of(b('severely reduced kicks'), b('prolonged stillness')) "
            "or count_true(b('reduced kicks'), b('excessive hiccups')) >= 2"
        ),
        "alert": "Seek same-day maternity assessment for markedly reduced or unusual fetal movements.",
        "recommendation_diet": "Do not skip meals. Use light nutrient-dense broths or porridges if your appetite is low, and take prescribed prenatal supplements.",
        "recommendation_activity": "Stop strenuous activity, rest on your side, and focus on fetal movement while arranging clinical assessment.",
        "recommendation_behavior": "Do not wait until tomorrow if movements are clearly reduced, absent for hours, or very different from usual.",
        "severity": "critical",
        "category": "medical",
        "enabled": True,
        "priority": 9,
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    {
        "rule_id": "alert.hyperemesis",
        "version": 1,
        "title": "Severe vomiting",
        "condition": "m('severe vomiting')",
        "alert": "Contact your clinician; severe vomiting can cause dehydration and may need treatment.",
        "recommendation_diet": "Try small frequent sips of clean fluid. Gentle fermented corn or sorghum porridges such as ogi, akamu, koko, or akasa may be easier to tolerate.",
        "recommendation_activity": "Rest in a cool, well-ventilated room and avoid heat exposure while symptoms are severe.",
        "recommendation_behavior": "Seek urgent care if you cannot keep fluids down, feel faint, have very dark urine, fever, or abdominal pain.",
        "severity": "high",
        "category": "medical",
        "enabled": True,
        "priority": 21,
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    {
        "rule_id": "alert.anemia",
        "version": 1,
        "title": "Possible anemia",
        "condition": (
            "count_true("
            "m('persistent fatigue'), "
            "m('weakness'), "
            "m('pallor'), "
            "m('shortness of breath on exertion'), "
            "m('dizziness'), "
            "m('lightheadedness'), "
            "m('rapid heartbeat'), "
            "m('irregular heartbeat')"
            ") >= 2"
        ),
        "alert": "Book a clinical check; these symptoms can fit anemia and may need blood tests or treatment.",
        "recommendation_diet": "Take prescribed iron-folate as directed. Pair iron-rich foods such as moringa leaf powder, dark leafy greens, turkey berries, eggs, fish, or beans with vitamin-C drinks like zobo/sobolo.",
        "recommendation_activity": "Pace your day, avoid overexertion, and sit down if you feel dizzy or short of breath.",
        "recommendation_behavior": "Ask your clinician about hemoglobin testing and whether multiple micronutrient supplements are appropriate for you.",
        "severity": "high",
        "category": "medical",
        "enabled": True,
        "priority": 23,
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    {
        "rule_id": "alert.cardiovascular",
        "version": 1,
        "title": "Cardiovascular warning symptoms",
        "condition": "any_of(m('chest pain'), m('heart palpitations'))",
        "alert": "Seek urgent medical advice for chest pain or strong palpitations in pregnancy.",
        "recommendation_diet": "Stay hydrated with clean water while arranging care. Avoid highly caffeinated or heavily sugared drinks.",
        "recommendation_activity": "Stop exertion immediately and rest in a cool, shaded, well-ventilated place.",
        "recommendation_behavior": "Avoid long walks, crowded transport, high heat, and high-pollution routes until you have been assessed.",
        "severity": "high",
        "category": "medical",
        "enabled": True,
        "priority": 24,
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    {
        "rule_id": "alert.gdm",
        "version": 1,
        "title": "Possible gestational diabetes (GDM)",
        "condition": (
            "count_true("
            "m('increased thirst'), "
            "m('increased urination'), "
            "m('blurred eyesight'), "
            "m('dry mouth'), "
            "m('persistent tiredness'), "
            "m('fatigue'), "
            "m('rapid weight gain')"
            ") >= 3"
        ),
        "alert": "Schedule a diagnostic glucose test; these symptoms can fit gestational diabetes.",
        "recommendation_diet": "Spread carbohydrates through the day. Prefer unrefined whole grains such as sorghum or millet and avoid added refined sugar or honey in porridges.",
        "recommendation_activity": "Moderate exercise can help glucose control; get a quick clinical check first, then continue safe activity and stay hydrated.",
        "recommendation_behavior": "Use washed bitterleaf only as a mild culinary vegetable. Never drink concentrated bitterleaf juice or medicinal agbo infusions during pregnancy.",
        "severity": "high",
        "category": "medical",
        "enabled": True,
        "priority": 20,
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    {
        "rule_id": "alert.lbw",
        "version": 1,
        "title": "Possible low birth weight risk",
        "condition": (
            "count_true("
            "b('reduced fetal movement'), "
            "b('reduced fetal rolling or stretching'), "
            "b('reduced kicking patterns'), "
            "m('no belly growth'), "
            "m('no visible belly growth'), "
            "m('low maternal weight gain'), "
            "m('dizziness'), "
            "m('poor appetite')"
            ") >= 3"
        ),
        "alert": "Review nutrition and contact your doctor; this pattern may indicate fetal growth risk.",
        "recommendation_diet": "Aim for nutrient-dense, calorie-adequate meals with enough protein. Add peanut butter, crayfish powder, moringa, Koko Plus, or fermented locust beans where appropriate.",
        "recommendation_activity": "Avoid heavy lifting and overexertion. Build rest into the day, especially in heat or poor air quality.",
        "recommendation_behavior": "If fetal movements are reduced or changed, seek assessment as soon as possible.",
        "severity": "high",
        "category": "medical",
        "enabled": True,
        "priority": 22,
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    {
        "rule_id": "alert.pm25.daily",
        "version": 1,
        "title": "PM2.5 is high",
        "condition": "ge_poll('pm25_avg_24h', 10)",
        "alert": "PM2.5 is high. Limit outdoor time and reduce smoke exposure today.",
        "recommendation_diet": "Maintain hydration and include antioxidant-rich fruits or vegetables when available.",
        "recommendation_activity": "Reduce outdoor exertion on high-PM days; schedule activity for cleaner hours or choose indoor light movement.",
        "recommendation_behavior": "Create the cleanest indoor air space you can. Keep windows closed during pollution peaks and use a fitted mask if you must go outside.",
        "severity": "moderate",
        "category": "air_quality",
        "enabled": True,
        "priority": 30,
        "cooldown_hours": 12,
        "ttl_hours": 12,
    },
    {
        "rule_id": "alert.heat.high",
        "version": 1,
        "title": "High heat exposure",
        "condition": "exists(aq.get('temperature')) and aq.get('temperature') >= 35",
        "alert": "Outdoor heat is high. Protect yourself from dehydration and overheating today.",
        "recommendation_diet": "Take frequent small sips of clean water. On extreme heat days, a small pinch of salt in water can help replace lost electrolytes if appropriate for you.",
        "recommendation_activity": "Move heavy chores, errands, exercise, and clinic travel to early morning or evening. Rest during the hottest midday hours.",
        "recommendation_behavior": "Stay in shaded, well-ventilated rooms, wear loose light clothing, and sit down immediately if you feel dizzy or lightheaded.",
        "severity": "moderate",
        "category": "air_quality",
        "enabled": True,
        "priority": 38,
        "cooldown_hours": 12,
        "ttl_hours": 12,
    },
    {
        "rule_id": "alert.cooking.solid_fuel",
        "version": 1,
        "title": "Solid-fuel cooking (wood/charcoal)",
        "condition": "lifestyle.get('cooking_method') in ('wood', 'charcoal')",
        "alert": "Wood or charcoal cooking can increase household smoke exposure.",
        "recommendation_diet": "Soak hard beans and grains overnight and use pot lids to shorten cooking time and reduce smoke.",
        "recommendation_activity": "Sit on a stool rather than bending over an open fire, and keep your body away from radiant heat and smoke.",
        "recommendation_behavior": "Cook outdoors or under an open-sided shelter when possible. Use dry small firewood, clear smoke before moving indoors, and fully extinguish coals after cooking.",
        "severity": "moderate",
        "category": "lifestyle",
        "enabled": True,
        "priority": 65,
        "cooldown_hours": 168,
        "ttl_hours": 168,
    },
    {
        "rule_id": "alert.cooking.indoor_solid_fuel",
        "version": 1,
        "title": "Indoor solid-fuel smoke risk",
        "condition": (
            "lifestyle.get('cooking_method') in ('wood', 'charcoal') and "
            "(lifestyle.get('cooking_venue') == 'indoor' or lifestyle.get('ventilation_level') == 'low')"
        ),
        "alert": "Indoor cooking smoke is high-risk during pregnancy.",
        "recommendation_diet": "Use quicker-cooking meals on smoky days and keep pots covered to reduce fuel use.",
        "recommendation_activity": "Avoid staying near the active hearth; ask someone else to manage the smokiest stage of cooking when possible.",
        "recommendation_behavior": "Open cross-ventilation, keep children and your belly away from the hearth, and clean chimney or stove draft paths weekly.",
        "severity": "moderate",
        "category": "lifestyle",
        "enabled": True,
        "priority": 64,
        "cooldown_hours": 168,
        "ttl_hours": 168,
    },
    {
        "rule_id": "alert.cooking.gas_and_no2_high",
        "version": 1,
        "title": "Gas cooking with high outdoor NO2",
        "condition": "lifestyle.get('cooking_method') == 'gas' and ge_poll('no2_24h_mean', 25)",
        "alert": "Outdoor NO2 is high. Gas cooking can add more indoor combustion pollution.",
        "recommendation_diet": "Keep your usual prenatal diet and stay hydrated.",
        "recommendation_activity": "Avoid vigorous activity near busy roads or in recently cooked, poorly ventilated rooms.",
        "recommendation_behavior": "Use a hood or open windows away from traffic while cooking. Prefer electric or induction cooking when available.",
        "severity": "info",
        "category": "lifestyle",
        "enabled": True,
        "priority": 66,
        "cooldown_hours": 48,
        "ttl_hours": 48,
    },
    {
        "rule_id": "alert.outdoor.midday",
        "version": 1,
        "title": "High midday outdoor exposure",
        "condition": (
            "lifestyle.get('time_spent') == 'mostly_outdoors' and "
            "lifestyle.get('time_of_day') == 'midday_or_afternoon'"
        ),
        "alert": "Your routine may expose you to peak heat and pollution.",
        "recommendation_diet": "Carry boiled, cooled water and take small sips regularly before you feel thirsty.",
        "recommendation_activity": "Shift heavy outdoor chores to early morning or after 5:30 PM, and take shaded seated breaks.",
        "recommendation_behavior": "Use shaded side streets, avoid traffic corridors and dust storms, and keep outdoor exposure short during peak sun.",
        "severity": "info",
        "category": "lifestyle",
        "enabled": True,
        "priority": 67,
        "cooldown_hours": 168,
        "ttl_hours": 168,
    },
]


NEW_RULE_IDS = {
    "alert.prom",
    "alert.fetal_hypoxia",
    "alert.hyperemesis",
    "alert.anemia",
    "alert.cardiovascular",
    "alert.heat.high",
    "alert.cooking.indoor_solid_fuel",
    "alert.outdoor.midday",
}


def forwards(apps, schema_editor):
    RecommendationRule = apps.get_model("recommendations", "RecommendationRule")
    for data in RULES:
        lookup = {"rule_id": data["rule_id"], "version": data["version"]}
        defaults = {k: v for k, v in data.items() if k not in lookup}
        RecommendationRule.objects.update_or_create(defaults=defaults, **lookup)


def backwards(apps, schema_editor):
    RecommendationRule = apps.get_model("recommendations", "RecommendationRule")
    RecommendationRule.objects.filter(rule_id__in=NEW_RULE_IDS, version=1).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0046_user_avatar"),
        ("recommendations", "0007_populate_recommendation_fields"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
