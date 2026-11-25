"""Map MASSIVE intents onto request-routing options. Drop ambiguous intents.

Option names are the labels sent to the models. The one-line description for
each option is sent to both decision models and chat LLMs, as the criterion
or as part of the system prompt. Ambiguous intents are dropped.
"""

from __future__ import annotations

# Labels in the request enum, in this order.
LABELS = ("Calendar", "SmartHome", "Media", "Orders", "Info", "Email")

# One-line description sent to every model, decision and chat alike.
LABEL_DESCRIPTIONS = {
    "Calendar": "Calendar and reminders: events, alarms, and personal to-do or shopping lists.",
    "SmartHome": "Smart home: lights, plugs, appliances, and other household devices.",
    "Media": "Media and volume: playing music, radio, podcasts, audiobooks, or games, and volume or playback settings.",
    "Orders": "Orders and transport: takeaway food, travel tickets, and ride bookings.",
    "Info": "Info lookup: facts, news, weather, time, conversions, recipes, currency, and stock prices.",
    "Email": "Email and contacts: reading or sending email, and looking up or adding contacts.",
}

# intent -> option. Only clear cases are included.
INTENT_TO_LABEL: dict[str, str] = {
    # Calendar and reminders, including personal lists.
    "calendar_set": "Calendar",
    "calendar_query": "Calendar",
    "calendar_remove": "Calendar",
    "alarm_set": "Calendar",
    "alarm_query": "Calendar",
    "alarm_remove": "Calendar",
    "lists_createoradd": "Calendar",
    "lists_query": "Calendar",
    "lists_remove": "Calendar",
    # Smart home devices.
    "iot_hue_lightchange": "SmartHome",
    "iot_hue_lightup": "SmartHome",
    "iot_hue_lightdim": "SmartHome",
    "iot_hue_lightoff": "SmartHome",
    "iot_hue_lighton": "SmartHome",
    "iot_wemo_off": "SmartHome",
    "iot_wemo_on": "SmartHome",
    "iot_cleaning": "SmartHome",
    "iot_coffee": "SmartHome",
    # Media playback and volume.
    "audio_volume_up": "Media",
    "audio_volume_down": "Media",
    "audio_volume_mute": "Media",
    "audio_volume_other": "Media",
    "play_music": "Media",
    "play_radio": "Media",
    "play_audiobook": "Media",
    "play_podcasts": "Media",
    "play_game": "Media",
    "music_settings": "Media",
    "music_likeness": "Media",
    "music_dislikeness": "Media",
    # Takeaway and transport bookings, not traffic or route questions.
    "takeaway_query": "Orders",
    "takeaway_order": "Orders",
    "transport_ticket": "Orders",
    "transport_taxi": "Orders",
    # Factual lookup, including currency and stock prices.
    "qa_factoid": "Info",
    "qa_definition": "Info",
    "qa_maths": "Info",
    "qa_stock": "Info",
    "qa_currency": "Info",
    "news_query": "Info",
    "weather_query": "Info",
    "datetime_query": "Info",
    "datetime_convert": "Info",
    "cooking_recipe": "Info",
    "cooking_query": "Info",
    # Email and contacts.
    "email_addcontact": "Email",
    "email_querycontact": "Email",
    "email_sendemail": "Email",
    "email_query": "Email",
}

# Intents present in MASSIVE that we do not force into a queue.
DROPPED_INTENTS: dict[str, str] = {
    "general_quirky": "Catch-all utterances, often off-intent.",
    "general_greet": "A greeting, not a request-routing queue.",
    "general_joke": "A joke request, not a request-routing queue.",
    "social_post": "Posting to a social feed, not one of the six queues.",
    "social_query": "Reading a social feed, not one of the six queues.",
    "recommendation_events": "Could be info lookup or local search; not forced.",
    "recommendation_locations": "Could be info lookup or local search; not forced.",
    "recommendation_movies": "Could be info lookup or media; not forced.",
    "music_query": "Could be media (the current track) or info lookup (who sings this); not forced.",
    "transport_query": "Route or timetable questions, not a booking; could be info or transport.",
    "transport_traffic": "Traffic conditions, not a booking; could be info or transport.",
}

CHOICE_INSTRUCTIONS = (
    "Route this user request to the queue that should handle it. "
    "Use the description of each option as the definition of that queue."
)

CHOICE_CRITERIA = dict(LABEL_DESCRIPTIONS)

LLM_SYSTEM = (
    "You route user requests to one queue. "
    "Reply with a JSON object that has a single field, label, "
    "which must be exactly one of: Calendar, SmartHome, Media, Orders, Info, Email. "
    "Use these descriptions as the definition of each queue:\n"
    + "\n".join(f"- {name}: {LABEL_DESCRIPTIONS[name]}" for name in LABELS)
    + " Do not include explanations or a self-reported confidence score."
)

USER_PREFIX = "Request:"


def label_for_intent(intent: str) -> str | None:
    return INTENT_TO_LABEL.get(intent)


def assert_mapping_complete(known_intents: set[str]) -> None:
    mapped = set(INTENT_TO_LABEL) | set(DROPPED_INTENTS)
    missing = known_intents - mapped
    extra = mapped - known_intents
    if missing or extra:
        raise RuntimeError(f"mapping gap: missing={sorted(missing)} extra={sorted(extra)}")
    overlap = set(INTENT_TO_LABEL) & set(DROPPED_INTENTS)
    if overlap:
        raise RuntimeError(f"intent both mapped and dropped: {sorted(overlap)}")
    bad = {k: v for k, v in INTENT_TO_LABEL.items() if v not in LABELS}
    if bad:
        raise RuntimeError(f"unknown labels in mapping: {bad}")
    if set(LABEL_DESCRIPTIONS) != set(LABELS):
        raise RuntimeError("LABEL_DESCRIPTIONS must cover every label")
