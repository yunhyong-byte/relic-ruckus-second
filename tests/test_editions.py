from io import BytesIO
import re
from pathlib import Path
from random import Random

from PIL import Image
import pytest
from streamlit.testing.v1 import AppTest

from flask_app import create_app
from relic import rules
from relic.database import Deck
from relic.editor import fields_for

SCRIPT = Path(__file__).resolve().parents[1] / "streamlit_app.py"


def form_value(html, name):
    return re.search(fr'name="{name}" value="([^"]+)"', html)[1]


@pytest.mark.parametrize("players", [1, 2, 3])
def test_browser_stale_posts_refresh_and_visibility(tmp_path, players):
    client = create_app(tmp_path / "flask.sqlite3").test_client()
    setup = client.get("/").get_data(as_text=True)
    token = form_value(setup, "form_token")
    data = {"form_token": token, "humans": players}
    data.update({f"player_{seat}": f"Player {seat}" for seat in range(1, players + 1)})
    response = client.post("/start", data=data, follow_redirects=True)
    hidden = response.get_data(as_text=True)
    assert response.headers["Cache-Control"] == "no-store"
    assert "data:image/" not in hidden
    assert hidden.count(f"<strong>{36 // (players + 1)}</strong>") == players + 1
    assert "Object and media details" not in hidden
    turn = {"form_token": token, "table_key": form_value(hidden, "table_key"),
            "revision": form_value(hidden, "revision"), "action": "reveal"}
    screen = client.post("/turn", data=turn, follow_redirects=True).get_data(as_text=True)
    assert client.post("/turn", data=turn, follow_redirects=True).get_data(as_text=True) == screen
    if "Call one stat" in screen:
        assert screen.count("data:image/") == 1
        turn.update(revision=form_value(screen, "revision"), action="choose", stat="Fragility")
        screen = client.post("/turn", data=turn, follow_redirects=True).get_data(as_text=True)
        assert client.post("/turn", data=turn, follow_redirects=True).get_data(as_text=True) == screen
    assert screen == client.get("/").get_data(as_text=True)
    assert "Public result" in screen
    assert screen.count("data:image/") == players + 1
    assert screen.count("<summary>Object and media details</summary>") == players + 1
    if "Next handoff" in screen:
        turn.update(revision=form_value(screen, "revision"), action="continue")
        next_screen = client.post("/turn", data=turn, follow_redirects=True).get_data(as_text=True)
        assert "Round 2" in next_screen and "data:image/" not in next_screen
        turn.update(action="reveal")
        assert client.post("/turn", data=turn, follow_redirects=True).get_data(as_text=True) == next_screen


def test_edit_in_browser_restart_streamlit_edit_there_and_restart_browser(tmp_path, monkeypatch):
    path = tmp_path / "both.sqlite3"
    monkeypatch.setenv("RELIC_DB_PATH", str(path))
    client = create_app(path).test_client()
    original = Deck(path).get("milla")
    index = client.get("/editor", query_string={"q": "margin", "category": "Manuscripts"})
    assert index.status_code == 200
    assert index.get_data(as_text=True).count('href="/editor/milla"') == 1
    assert 'href="/editor/pavo"' not in index.get_data(as_text=True)
    html = client.get("/editor/milla").get_data(as_text=True)
    token = form_value(html, "form_token")
    fields = {**fields_for(original), "Fragility": "13", "bio": "A change from the Flask editor. It survived.",
              "ref_notes": "A catalogue note saved in Flask.",
              "revision": str(original.revision), "form_token": token, "action": "preview"}
    portrait = BytesIO()
    Image.new("RGB", (16, 16), "orange").save(portrait, "PNG")
    image_bytes = portrait.getvalue()
    fields.update(image=(BytesIO(image_bytes), "test.png"), alt="Orange playtest sample",
                  image_source="Playtest file", image_creator="Test creator",
                  image_rights="CC0 1.0", image_credit="Test photo credit")
    response = client.post("/editor/milla", data=fields)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Draft preview" in html and "<dd>13</dd>" in html
    assert re.search(r'src="data:image/png;base64,[^"]+" alt="Orange playtest sample"', html)
    assert Deck(path).get("milla") == original
    response = client.post("/editor/milla", data={"action": "save", "form_token": token,
                           "draft_token": form_value(html, "draft_token")})
    assert response.status_code == 303

    app = AppTest.from_file(str(SCRIPT)).run()
    assert not app.exception
    app.radio[0].set_value("Deck editor").run()
    app.text_input[0].set_value("Milla Margin").run()
    assert not app.exception
    assert app.number_input[0].value == 13
    assert "Flask editor" in app.text_area[1].value
    reference_notes = next(widget for widget in app.text_area if widget.label == "More about this reference")
    assert reference_notes.value == "A catalogue note saved in Flask."
    reference_notes.set_value("A catalogue note saved in Streamlit.")
    app.number_input[0].set_value(19)
    app.text_area[1].set_value("Changed in Streamlit. The rabbit approves.")
    app.button[0].click().run()
    assert not app.exception
    assert any(button.label == "Save changes" for button in app.button)
    next(button for button in app.button if button.label == "Save changes").click().run()
    assert not app.exception

    reopened = create_app(path).test_client()
    saved = reopened.get("/editor/milla").get_data(as_text=True)
    assert "<dd>19</dd>" in saved and "The rabbit approves." in saved
    assert "A catalogue note saved in Streamlit." in saved
    assert Deck(path).get("milla").image == image_bytes

    # This deal makes Milla the first human leader's top card in both editions.
    monkeypatch.setattr(rules, "Random", lambda: Random(50))
    home = reopened.get("/").get_data(as_text=True)
    token = form_value(home, "form_token")
    handoff = reopened.post("/start", follow_redirects=True, data={
        "form_token": token, "humans": 1, "player_1": "Jo",
    }).get_data(as_text=True)
    private = reopened.post("/turn", follow_redirects=True, data={
        "form_token": token, "table_key": form_value(handoff, "table_key"),
        "revision": form_value(handoff, "revision"), "action": "reveal",
    }).get_data(as_text=True)
    assert "<h3>Dame Milla Margin</h3>" in private and "<strong>19</strong>" in private
    assert "<summary>Object and media details</summary>" in private
    assert original.reference.media_url in private

    app.radio[0].set_value("Play").run()
    app.text_input[0].set_value("Jo")
    app.button[0].click().run()
    app.button[0].click().run()
    assert not app.exception
    assert app.button[0].label == "Fragility · 19"
    assert any("Orange playtest sample" in element.value for element in app.get("html"))
    assert any("Object and media details" in element.value and original.reference.media_url in element.value
               for element in app.get("html"))



def test_streamlit_match_recovers_on_new_session_without_playing_twice(tmp_path, monkeypatch):
    monkeypatch.setenv("RELIC_DB_PATH", str(tmp_path / "stream.sqlite3"))
    app = AppTest.from_file(str(SCRIPT)).run()
    app.radio[1].set_value(3).run()
    for field, name in zip(app.text_input, ("Jo", "Sam", "Alex")):
        field.set_value(name)
    app.button[0].click().run()
    assert not app.exception
    key = app.query_params["table"]

    def all_html(test_app):
        return " ".join(element.value for element in test_app.get("html"))

    recovered = AppTest.from_file(str(SCRIPT))
    recovered.query_params["table"] = key
    recovered.run()
    assert not recovered.exception
    handoff = all_html(recovered)
    assert "ROUND 1" in handoff and handoff.count("<b>9</b>") == 4
    assert "data:image/" not in handoff
    recovered.button[0].click().run()
    if recovered.button[0].label.startswith("Fragility"):
        assert all_html(recovered).count("data:image/") == 1
        recovered.button[0].click().run()
    assert recovered.caption[0].value.startswith("Public result")
    assert all_html(recovered).count("data:image/") == 4
    before = all_html(recovered)
    recovered.run()
    assert not recovered.exception
    assert before == all_html(recovered)


def test_old_flask_forms_cannot_reveal_a_new_match(tmp_path):
    client = create_app(tmp_path / "flask.sqlite3").test_client()
    token = form_value(client.get("/").get_data(as_text=True), "form_token")
    setup = {"form_token": token, "humans": 1, "player_1": "Jo"}
    first = client.post("/start", data=setup, follow_redirects=True).get_data(as_text=True)
    key = form_value(first, "table_key")
    client.post("/leave", data={"form_token": token, "table_key": key})
    setup["player_1"] = "Sam"
    second = client.post("/start", data=setup, follow_redirects=True).get_data(as_text=True)
    assert form_value(second, "table_key") != key
    stale = {"form_token": token, "table_key": key, "revision": 0, "action": "reveal"}
    assert client.post("/turn", data=stale, follow_redirects=True).get_data(as_text=True) == second
