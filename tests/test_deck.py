from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from random import Random
import sqlite3

from PIL import Image
import pytest

from relic.cards import CATEGORIES, MODES, STATS, validate_card
from relic.database import COLUMNS, SCHEMA, Deck, StaleEdit, to_row
from relic.editor import fields_for, make_draft
from relic.rules import Game
from relic.seed import ART, GALLERIES, seed_cards


def test_seeded_deck_has_distinct_decodable_art_and_balanced_scores(tmp_path):
    deck = Deck(tmp_path / "deck.sqlite3").snapshot()
    assert Counter(card.category for card in deck) == dict.fromkeys(CATEGORIES, 6)
    assert len({card.name for card in deck}) == len({card.id for card in deck}) == 36
    assert len({card.scores for card in deck}) == 36
    assert len({sha256(card.image).hexdigest() for card in deck}) == 36
    assert {path.stem for path in ART.glob("*.webp")} == {card.id for card in deck}
    assert len({card.reference.record_url for card in deck}) == 36
    for card in deck:
        validate_card(card)
        assert card.reference.links and card.reference.metadata
        assert card.reference.media_kind in ({"Audio", "Video"} if card.category == CATEGORIES[-1] else {"Image"})
        assert card.image == (ART / f"{card.id}.webp").read_bytes()
        assert card.mime == "image/webp" and card.shows_image and card.description
        with Image.open(BytesIO(card.image)) as image:
            image.load()
            assert image.size == (540, 540)
        assert max(sum(other.score(stat) < card.score(stat) for other in deck) for stat in STATS) >= 16
    columns = list(zip(*(card.scores for card in deck)))
    for column in columns:
        assert max(column) - min(column) >= 55
        assert 25 <= len(set(column)) < 36  # Distinct full profiles still allow tie rounds.
    maxima = tuple(max(column) for column in columns)
    assert not any(card.scores == maxima for card in deck)


def test_init_concurrency_edit_reopen_snapshot_and_revision(tmp_path):
    path = tmp_path / "shared.sqlite3"
    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.map(Deck, (path, path))
    original = first.get("milla")
    old_match = Game(["Jo"], first.snapshot(), Random(5))
    reference = replace(original.reference, notes="Notes from a playtester.")
    draft = replace(original, scores=(12, *original.scores[1:]), bio="Museum playtest. A second sentence.",
                    reference=reference)
    second.save(draft)
    reopened = Deck(path)
    new_match = Game(["Jo"], reopened.snapshot(), Random(5))
    assert old_match.deck["milla"] == original
    assert new_match.deck["milla"].score("Fragility") == 12
    assert new_match.deck["milla"].bio == draft.bio
    assert new_match.deck["milla"].image == original.image
    assert new_match.deck["milla"].reference == reference
    with pytest.raises(StaleEdit):
        first.save(draft)


def test_editor_validates_images_credits_and_all_display_modes(tmp_path):
    deck = Deck(tmp_path / "local.sqlite3")
    card = deck.get("milla")
    values = fields_for(card)
    values["Value"] = "101"
    with pytest.raises(ValueError, match="six stats"):
        make_draft(card, values)
    values["Value"] = "52"
    with pytest.raises(ValueError, match="decoded"):
        make_draft(card, values, upload=b"corrupt")
    with pytest.raises(ValueError, match="http or https"):
        make_draft(card, {**values, "ref_media_url": "javascript:alert(1)"})

    picture = BytesIO()
    Image.new("RGB", (3, 3), "orange").save(picture, "PNG")
    new_values = {
        **values,
        "alt": "An orange square",
        "archive": "An archival example.",
        "image_source": "https://example.org/images/relic-12",
        "image_creator": "Image maker",
        "image_rights": "CC0 1.0",
        "image_credit": "Image collection, record 12",
        "text_source": "https://example.org/archive/text-6",
        "text_creator": "Text author",
        "text_rights": "Public domain",
        "text_credit": "Text collection, record 6",
    }
    for mode in MODES:
        current = deck.get("milla")
        draft = make_draft(current, {**new_values, "mode": mode},
                           upload=picture.getvalue() if mode == MODES[0] else None)
        deck.save(draft)
        saved = deck.get("milla")
        assert saved.mime == "image/png"
        assert saved.text_credit.creator == "Text author"
        assert saved.image_credit.creator == "Image maker"
        assert saved.description == ("" if mode == "Image only" else new_values["archive"])
        assert saved.shows_image == (mode != "Description only")
        assert saved.image == picture.getvalue()
    remove = make_draft(saved, {**new_values, "mode": MODES[2]}, remove=True)
    deck.save(remove)
    assert deck.get("milla").image is None


def test_old_database_gains_references_without_losing_edits(tmp_path):
    path = tmp_path / "previous-release.sqlite3"
    old_subjects = {row[0]: row[2] for gallery in GALLERIES for row in gallery}
    legacy = [replace(card, subject=old_subjects[card.id], reference=None) for card in seed_cards()]
    first = legacy[0]
    played = replace(first, subject="My preferred subject", bio="A playtest biography.",
                     scores=(12, *first.scores[1:]), revision=4)
    legacy[0] = played
    legacy_columns = [column for column in COLUMNS if column != "object_reference"]
    placeholders = ", ".join("?" for _ in legacy_columns)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO metadata VALUES ('deck_seeded')")
        connection.execute(SCHEMA.replace("    object_reference TEXT,\n", ""))
        connection.executemany(
            f"INSERT INTO cards ({', '.join(legacy_columns)}) VALUES ({placeholders})",
            ([value for column, value in zip(COLUMNS, to_row(card)) if column != "object_reference"]
             for card in legacy),
        )

    upgraded = Deck(path).snapshot()
    assert len(upgraded) == 36 and all(card.reference for card in upgraded)
    current = next(card for card in upgraded if card.id == played.id)
    assert replace(current, reference=None, revision=played.revision) == played
    assert current.revision == played.revision + 1
    assert next(card for card in upgraded if card.id == "pavo").subject != old_subjects["pavo"]
    assert Deck(path).snapshot() == upgraded
