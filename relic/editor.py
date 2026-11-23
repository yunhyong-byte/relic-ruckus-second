"""The same draft fields and validation are used in both local editors."""
from dataclasses import replace

from relic.cards import Credit, STATS, image_mime, validate_card
from relic.references import ObjectReference, REFERENCE_FIELDS

TEXT_FIELDS = {
    "name": "Character name", "subject": "Object or tradition",
    "category": "Category", "heritage": "Heritage description", "bio": "Comic biography",
    "mode": "Display mode", "alt": "Image alt text", "archive": "Archival description",
}
CREDIT_FIELDS = {"source": "Source URL or identifier", "creator": "Creator",
                 "rights": "Rights statement or licence", "credit": "Required credit line"}


def fields_for(card):
    fields = {field: getattr(card, field) for field in TEXT_FIELDS}
    fields.update({stat: str(card.score(stat)) for stat in STATS})
    reference = card.reference or ObjectReference()
    fields.update({f"ref_{field}": getattr(reference, field) for field in REFERENCE_FIELDS})
    for kind in ("image", "text"):
        credit = getattr(card, f"{kind}_credit")
        fields.update({f"{kind}_{field}": getattr(credit, field) for field in CREDIT_FIELDS})
    return fields


def make_draft(card, fields, *, upload=None, remove=False):
    try:
        scores = tuple(int(fields[stat]) for stat in STATS)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Enter a whole number from 1 to 100 for each of the six stats.") from error
    if remove and upload is not None:
        raise ValueError("Choose either to remove the current image or to upload a replacement.")
    credits = {
        f"{kind}_credit": Credit(*(fields.get(f"{kind}_{field}", "").strip() for field in CREDIT_FIELDS))
        for kind in ("image", "text")
    }
    image = None if remove else card.image
    mime = None if remove else card.mime
    if upload is not None:
        image, mime = upload, image_mime(upload)
    if remove:
        credits["image_credit"] = Credit()
    original = card.reference or ObjectReference()
    reference_fields = {
        field: fields.get(f"ref_{field}", getattr(original, field)).strip()
        for field in REFERENCE_FIELDS
    }
    reference = ObjectReference(**reference_fields) if card.reference or any(reference_fields.values()) else None
    draft = replace(
        card, **{field: fields.get(field, "").strip() for field in TEXT_FIELDS},
        scores=scores, image=image, mime=mime, reference=reference, **credits,
    )
    validate_card(draft)
    return draft


def filter_cards(summaries, query="", category="All galleries"):
    query = query.strip().casefold()
    return [
        card for card in summaries
        if (category == "All galleries" or card["category"] == category)
        and (not query or query in f"{card['name']} {card['subject']} {card['category']}".casefold())
    ]
