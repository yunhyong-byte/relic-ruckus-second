"""The shared SQLite deck. Neither edition keeps its own copy."""
from contextlib import closing, contextmanager
from dataclasses import asdict
from pathlib import Path
import json
import os
import sqlite3

from relic.cards import Card, Credit, validate_card
from relic.reference_data import REFERENCES
from relic.references import ObjectReference
from relic.seed import GALLERIES, seed_cards

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "relic_ruckus.sqlite3"
SCORE_COLUMNS = ("fragility", "value", "aesthetics", "popularity", "cultural_meaning", "emotion")
CREDIT_FIELDS = ("source", "creator", "rights", "credit")
COLUMNS = (
    "id", "name", "subject", "category", "heritage", "bio", *SCORE_COLUMNS, "alt",
    "image", "mime", *(f"image_{field}" for field in CREDIT_FIELDS), "archive",
    *(f"text_{field}" for field in CREDIT_FIELDS), "mode", "object_reference", "revision",
)
SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    subject TEXT NOT NULL,
    category TEXT NOT NULL,
    heritage TEXT NOT NULL,
    bio TEXT NOT NULL,
    fragility INTEGER NOT NULL CHECK(fragility BETWEEN 1 AND 100),
    value INTEGER NOT NULL CHECK(value BETWEEN 1 AND 100),
    aesthetics INTEGER NOT NULL CHECK(aesthetics BETWEEN 1 AND 100),
    popularity INTEGER NOT NULL CHECK(popularity BETWEEN 1 AND 100),
    cultural_meaning INTEGER NOT NULL CHECK(cultural_meaning BETWEEN 1 AND 100),
    emotion INTEGER NOT NULL CHECK(emotion BETWEEN 1 AND 100),
    alt TEXT NOT NULL,
    image BLOB,
    mime TEXT,
    image_source TEXT NOT NULL,
    image_creator TEXT NOT NULL,
    image_rights TEXT NOT NULL,
    image_credit TEXT NOT NULL,
    archive TEXT NOT NULL,
    text_source TEXT NOT NULL,
    text_creator TEXT NOT NULL,
    text_rights TEXT NOT NULL,
    text_credit TEXT NOT NULL,
    mode TEXT NOT NULL,
    object_reference TEXT,
    revision INTEGER NOT NULL
)
"""
INSERT = f"INSERT INTO cards ({', '.join(COLUMNS)}) VALUES ({', '.join('?' for _ in COLUMNS)})"


class StaleEdit(ValueError):
    """Someone saved a newer revision after the editor was opened."""


def to_row(card):
    values = asdict(card)
    values.update(zip(SCORE_COLUMNS, values.pop("scores")))
    reference = values.pop("reference")
    values["object_reference"] = json.dumps(reference, ensure_ascii=False) if reference else None
    for kind in ("image", "text"):
        credit = values.pop(f"{kind}_credit")
        values.update({f"{kind}_{field}": value for field, value in credit.items()})
    return tuple(values[column] for column in COLUMNS)


def from_row(row):
    values = dict(row)
    values["scores"] = tuple(values.pop(column) for column in SCORE_COLUMNS)
    reference = values.pop("object_reference")
    values["reference"] = ObjectReference(**json.loads(reference)) if reference else None
    for kind in ("image", "text"):
        values[f"{kind}_credit"] = Credit(*(values.pop(f"{kind}_{field}") for field in CREDIT_FIELDS))
    return Card(**values)


class Deck:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("RELIC_DB_PATH") or DEFAULT_PATH).expanduser().resolve()
        self.initialise()

    @contextmanager
    def connect(self):
        # SQLite's transaction context commits or rolls back without closing the file.
        with closing(sqlite3.connect(self.path, timeout=20)) as connection, connection:
            connection.row_factory = sqlite3.Row
            yield connection

    def initialise(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            # Take the write lock before checking the marker, so both apps can start together.
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY)")
            connection.execute(SCHEMA)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(cards)")}
            needs_references = "object_reference" not in columns
            if needs_references:
                connection.execute("ALTER TABLE cards ADD COLUMN object_reference TEXT")
            if not connection.execute("SELECT 1 FROM metadata WHERE key = 'deck_seeded'").fetchone():
                connection.executemany(INSERT, (to_row(card) for card in seed_cards()))
                connection.execute("INSERT INTO metadata VALUES ('deck_seeded')")
            elif needs_references:
                # Add the new reference to old decks and keep any subject a playtester changed.
                rows = []
                for gallery in GALLERIES:
                    for card_id, _, old_subject, *_ in gallery:
                        subject, reference = REFERENCES[card_id]
                        rows.append((json.dumps(asdict(reference), ensure_ascii=False), old_subject, subject, card_id))
                connection.executemany(
                    """UPDATE cards
                       SET object_reference = ?, subject = CASE WHEN subject = ? THEN ? ELSE subject END,
                           revision = revision + 1
                       WHERE id = ?""",
                    rows,
                )

    def snapshot(self):
        with self.connect() as connection:
            return tuple(from_row(row) for row in connection.execute("SELECT * FROM cards ORDER BY id"))

    def summaries(self):
        with self.connect() as connection:
            return connection.execute("SELECT id, name, subject, category FROM cards ORDER BY name").fetchall()

    def get(self, card_id):
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        return from_row(row) if row else None

    def save(self, card):
        validate_card(card)
        assignments = ", ".join(f"{column} = ?" for column in COLUMNS[1:-1])
        with self.connect() as connection:
            cursor = connection.execute(
                f"UPDATE cards SET {assignments}, revision = revision + 1 WHERE id = ? AND revision = ?",
                (*to_row(card)[1:-1], card.id, card.revision),
            )
            if cursor.rowcount != 1:
                raise StaleEdit("This card changed while you were editing. Reopen it and apply your changes.")
