"""Catalogue and media fields for the real references on Relic Ruckus cards."""
from dataclasses import dataclass
from urllib.parse import urlsplit

MEDIA_KINDS = ("Image", "Audio", "Video")
REFERENCE_FIELDS = {
    "title": "Catalogue title or recording",
    "collection": "Held or documented by",
    "date": "Date or period",
    "origin": "Origin or community",
    "material": "Medium or format",
    "identifier": "Catalogue or recording ID",
    "notes": "More about this reference",
    "record_url": "Catalogue record URL",
    "media_kind": "Media type",
    "media_url": "Image, audio or video URL",
}


def is_source_link(source):
    try:
        parts = urlsplit(source)
        return (
            parts.scheme in {"http", "https"} and bool(parts.hostname)
            and parts.username is None and not any(char.isspace() for char in source)
        )
    except ValueError:
        return False


@dataclass(frozen=True)
class ObjectReference:
    title: str = ""
    collection: str = ""
    date: str = ""
    origin: str = ""
    material: str = ""
    identifier: str = ""
    notes: str = ""
    record_url: str = ""
    media_kind: str = ""
    media_url: str = ""

    @property
    def metadata(self):
        return [
            (REFERENCE_FIELDS[field], getattr(self, field))
            for field in ("collection", "date", "origin", "material", "identifier")
            if getattr(self, field)
        ]

    @property
    def links(self):
        media_label = {
            "Image": "View the object image",
            "Audio": "Listen to the recording",
            "Video": "Watch the video",
        }[self.media_kind]
        if self.media_url and self.media_url != self.record_url:
            return ((media_label, self.media_url), ("Open the catalogue record", self.record_url))
        return ((media_label, self.record_url),)

    def validate(self):
        for field, label in REFERENCE_FIELDS.items():
            value = getattr(self, field)
            if field not in {"identifier", "media_url"} and not value:
                raise ValueError(f"Enter {label.lower()} for the object details.")
            if len(value) > (2000 if field.endswith("_url") else 600):
                raise ValueError(f"{label} is too long.")
        if self.media_kind not in MEDIA_KINDS:
            raise ValueError("Choose Image, Audio or Video for the object details.")
        if not is_source_link(self.record_url) or (self.media_url and not is_source_link(self.media_url)):
            raise ValueError("Enter a valid http or https address for the catalogue and any media link.")
