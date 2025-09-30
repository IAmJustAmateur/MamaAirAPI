# choices_emojis.py (например)
WORK_TYPE_EMOJI = {
    "Desk": "🪑",
    "Standing": "🧍‍♀️",
    "Night Shift": "🌖",
    "Physical": "👩‍🌾",
    "Care": "🧑‍⚕️",  # при желании: 👩‍👧‍👧 для stay-at-home parent
    "Field": "🌾",
    "Domestic": "👩‍👧‍👧",
}

DIET_TYPE_EMOJI = {
    "carnivore": "🥩",
    "vegetarian": "🥗",
}

COOKING_METHOD_EMOJI = {
    "wood": "🪵",
    "charcoal": "🪨",
    "gas": "⛽️",
    "electric": "🔌",
}


def map_choices_with_emoji(choices, emoji_map=None):
    result = []
    for value, label in choices:
        item = {"value": value, "label": str(label)}
        if emoji_map:
            emoji = emoji_map.get(value)
            if emoji:
                item["emoji"] = emoji
                item["label_with_emoji"] = f"{emoji} {item['label']}"
        result.append(item)
    return result
