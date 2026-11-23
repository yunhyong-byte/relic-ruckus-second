"""Card fields and validation shared by the two editors."""
from dataclasses import dataclass
from io import BytesIO
from PIL import Image

from relic.references import ObjectReference

STATS = {
    "Fragility": "How delicate the object is. A higher score means more delicate.",
    "Value": "The appraisal the character imagines their museum would give.",
    "Aesthetics": "How striking the character finds the object or performance.",
    "Popularity": "How big a crowd the character expects it to draw.",
    "Cultural Meaning": "How important it is to the community in the character's story.",
    "Emotion": "How strongly it moves the character or their audience.",
}
CATEGORIES = (
    "Manuscripts", "Paintings", "Sculpture", "Archaeological finds",
    "Textiles and craftwork", "Intangible heritage",
)
MODES = ("Image and description", "Image only", "Description only")
FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class Credit:
    source: str = ""
    creator: str = ""
    rights: str = ""
    credit: str = ""


@dataclass(frozen=True)
class Card:
    id: str
    name: str
    subject: str
    category: str
    heritage: str
    bio: str
    scores: tuple[int, ...]
    alt: str
    image: bytes | None = None
    mime: str | None = None
    image_credit: Credit = Credit()
    archive: str = ""
    text_credit: Credit = Credit()
    mode: str = MODES[0]
    reference: ObjectReference | None = None
    revision: int = 0

    def score(self, stat):
        return self.scores[tuple(STATS).index(stat)]

    @property
    def shows_image(self):
        return bool(self.image) and self.mode != "Description only"

    @property
    def description(self):
        if self.mode == "Image only":
            return ""
        return self.archive or self.heritage


def image_mime(data):
    """Check the decoded file instead of trusting its filename or upload header."""
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Choose a PNG, JPEG or WebP image up to 5 MB.")
    try:
        with Image.open(BytesIO(data)) as picture:
            mime = FORMATS.get(picture.format)
            if not mime or picture.width * picture.height > 16_000_000:
                raise ValueError("Use a PNG, JPEG or WebP up to 16 megapixels.")
            if getattr(picture, "is_animated", False):
                raise ValueError("Choose a still image.")
            picture.verify()
        with Image.open(BytesIO(data)) as picture:
            picture.load()
    except (OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise ValueError("The image could not be decoded.") from error
    return mime


def validate_credit(credit, label):
    if not all((credit.source, credit.creator, credit.rights, credit.credit)):
        raise ValueError(f"Enter the source, creator, rights statement and credit for {label}.")
    if any(len(value) > 500 for value in vars(credit).values()):
        raise ValueError(f"Keep each {label} credit field within 500 characters.")


def validate_card(card):
    if card.category not in CATEGORIES or card.mode not in MODES:
        raise ValueError("Choose a listed category and display mode.")
    for label, value, limit in (
        ("Character name", card.name, 80), ("Object or tradition", card.subject, 120),
        ("Heritage description", card.heritage, 1000), ("Comic biography", card.bio, 2000),
    ):
        if not value or len(value) > limit:
            raise ValueError(f"{label} must have 1 to {limit} characters.")
    if len(card.scores) != len(STATS) or any(
        type(score) is not int or not 1 <= score <= 100 for score in card.scores
    ):
        raise ValueError("Enter a whole number from 1 to 100 for each of the six stats.")
    if card.mode != "Description only" and not card.image:
        raise ValueError("Upload an image or choose Description only.")
    if card.image:
        if not card.alt or len(card.alt) > 300:
            raise ValueError("Enter alt text of 1 to 300 characters for the image.")
        if image_mime(card.image) != card.mime:
            raise ValueError("The saved image type does not match the file.")
        validate_credit(card.image_credit, "the image")
    if len(card.archive) > 2000:
        raise ValueError("Keep the archival description within 2,000 characters.")
    if card.archive:
        validate_credit(card.text_credit, "the archival text")
    if card.reference:
        card.reference.validate()
