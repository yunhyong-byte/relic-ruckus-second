# Relic Ruckus

A shared-device card game for **one to three humans and one computer**. Each of the 36 original fantasy characters tends a replica tied to a specific catalogue object. Six cards also link those objects to living practices, with recordings of performances or demonstrations. The heritage notes describe the real subjects. The biographies and numerical ratings are invented for the game.

## Set up

Install Python 3.10 or later. Unpack the source archive if you received one, then open a terminal in the `relic-ruckus` folder.

On macOS or Linux, run

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell, run

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

PowerShell can also run the commands below with `.\.venv\Scripts\python.exe` in place of `python` if activation is unavailable.

## Launch either edition

**Flask browser edition**

```sh
python -m flask --app flask_app run --host 127.0.0.1 --port 5050
```

Open <http://127.0.0.1:5050>.

**Streamlit edition**

```sh
python -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

Open <http://127.0.0.1:8501>. To run both together, use two terminals in the same repository folder with the virtual environment active in each. Press Ctrl+C in a server's terminal to stop that edition.

## Play a match

1. Choose how many humans are playing, enter their names and deal. The game randomly chooses a dealer, deals all 36 cards, and starts with the seat to the dealer's left.
2. Pass the device to the named leader. They reveal their own top card and call one of its six stats. When the computer leads, the table can reveal its choice and the result together.
3. Compare the cards. Highest wins on every stat, including Fragility. The collector puts the played cards and any pot at the bottom of their pile, then leads.
4. If the high score ties, the cards go into the pot. Everyone with cards compares again on the same stat, including lower scorers. One remaining contributor takes the pot. If no one can contribute, the top scorers on the last comparison share the match.
5. Collect all 36 cards for a sole win. The in-game rules are available throughout the match.

## Explore the collection

Open **Object and media details** on a revealed card or its editor preview. It shows the holding institution, date or period, origin, materials, and the catalogue number where one is available. It also links to a photograph, scan, recording, or video. Some images open in the collection record's viewer. The editor's **Edit object and media details** section lets you update the metadata or replace a link.

The card portraits are original fantasy illustrations. The linked images and recordings remain with their publishers. Check the source's terms if you plan to reuse any linked media.

## Change a score and replace a portrait after a playtest

Suppose Dame Milla Margin's Fragility of 94 won more often than you expected. To try a score of 88 along with a new portrait:

1. Make an original photo or illustration of a paper rabbit beside an open notebook. Save it as `milla-playtest.png`. You can also use a still JPEG or WebP. Keep the image under 5 MB and 16 megapixels.
2. In either edition, open **Deck editor**. Search for **Milla Margin**, or filter by **Manuscripts**, then open her card.
3. Change **Fragility** from **94** to **88**. Choose **Image and description** and upload `milla-playtest.png` under **Replacement image**.
4. Set **Image alt text** to a concise description of your picture, such as “A folded paper rabbit sits next to a hand-drawn illuminated notebook.”
5. Fill in the four **Image credit** fields for that specific file. For your own photo, use a source identifier such as `milla-playtest.png, personal collection`, your name as creator, a rights statement such as `Original photo, used with creator permission`, and a credit line such as `Photograph by Jo, used with permission`. For an archival image, enter the object-level image source, its creator, the exact public-domain or CC0 declaration or licence terms, and the required credit.
6. Select **Preview changes**. Check the new portrait and the displayed rating of **88**, then select **Save changes**. The same card in the other edition's editor now shows the change. Start a new match there to use the updated deck.

Use **Image only** to hide the heritage caption, or **Description only** to hide the portrait. The fictional biography remains available in all three modes. An archival description can replace the displayed heritage caption. If you enter one, fill in the separate **Archival text credit** fields for that text. A description-only card can keep its stored portrait for later or remove it with **Remove the stored image**.

## Where the data lives

Both editions open `data/relic_ruckus.sqlite3` inside the repository. The first launch creates that file and seeds the 36 cards from `relic/seed.py`, `relic/reference_data.py` and `relic/art/`. The initialisation transaction seeds only once. Edits subsequently live in SQLite, including uploaded image bytes, detected MIME types, each image or text credit, and the object references.

When a deck from the first release is opened, it gains the catalogue details automatically. The upgrade retains your saved edits and replaces the old subject label only where it still matches the original seed.

A new match reads a snapshot from SQLite. An existing match continues with the cards and ratings it started with. Refreshes and Streamlit reruns preserve the current screen while the edition's server is running. Restarting a server starts fresh tables and keeps saved deck edits.

To use a different deck file, set the environment variable `RELIC_DB_PATH` to the **same absolute path** in both terminals before launching. To back up your edits, stop both editions and copy the SQLite file.

## Find your way around the Python

- `relic/rules.py` deals the cards, chooses the computer's stat and resolves rounds. Tests can pass a seeded `random.Random`.
- `relic/room.py` keeps the current match on its server. Screen revision numbers protect against repeated clicks and stale forms.
- `relic/database.py` initialises and reads the SQLite deck. `relic/editor.py` and `relic/cards.py` turn both editors' input into validated card updates.
- `streamlit_app.py` is the Streamlit interface. `flask_app.py`, `templates/` and `static/` make up the browser interface.
- `relic/seed.py` contains the biographies, descriptions, alt text and ratings. The WebP images in `relic/art/` are used when creating a fresh database, one image per stable card ID.
- `relic/reference_data.py` contains the 36 researched object records and media links. Each entry pairs the short card label with the catalogue details.

## Run the tests

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The suite tests full matches with every player count, card conservation, the computer's three-stat choice, tie cases, a last-card win, stale actions, SQLite persistence and edits in both editions. It also checks that all 36 portraits decode, that no two score profiles are identical, and that each stat has a useful range and some ties. All 36 portraits were visually checked against their assigned characters and props.

The browser edition bundles DM Sans and DM Serif Text under the SIL Open Font License. Their notices are in `static/fonts/`.
