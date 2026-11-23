"""Run locally with python -m streamlit run streamlit_app.py."""
from base64 import b64encode
from html import escape
from pathlib import Path
import os

import streamlit as st

from relic.cards import CATEGORIES, MODES, STATS
from relic.copy import result_message, winners_message
from relic.database import Deck
from relic.editor import CREDIT_FIELDS, TEXT_FIELDS, fields_for, filter_cards, make_draft
from relic.references import MEDIA_KINDS, REFERENCE_FIELDS, is_source_link
from relic.room import Tables
from relic.rules import Game, RULES

STATIC = Path(__file__).resolve().parent / "static"


@st.cache_resource
def get_deck(path):
    return Deck(path)


@st.cache_resource
def get_tables():
    # A hard refresh opens another Streamlit session. The random URL table ID
    # lets the new session recover the current screen from this server process.
    return Tables()


def render_credits(card):
    lines = []
    for label, credit, visible in (
        ("Image", card.image_credit, card.shows_image),
        ("Archival text", card.text_credit, card.archive and card.description),
    ):
        if visible:
            source = escape(credit.source)
            if is_source_link(credit.source):
                source = f'<a href="{source}" rel="noreferrer">Source</a>'
            details = " · ".join(escape(text) for text in (credit.credit, credit.creator, credit.rights))
            lines.append(f'<p class="relic-credit"><strong>{label}</strong> · {details} · {source}</p>')
    return "".join(lines)


def render_reference(card):
    reference = card.reference
    if reference is None:
        return ""
    title = f"<p><strong>{escape(reference.title)}</strong></p>" if reference.title != card.subject else ""
    fields = "".join(
        f"<div><dt>{escape(label)}</dt><dd>{escape(value)}</dd></div>"
        for label, value in reference.metadata
    )
    links = "".join(
        f'<li><a href="{escape(url)}" target="_blank" rel="noopener noreferrer">{escape(label)} ↗</a></li>'
        for label, url in reference.links if is_source_link(url)
    )
    return (
        f'<details class="relic-object"><summary>Object and media details</summary>{title}'
        f'<dl>{fields}</dl><p>{escape(reference.notes)}</p><ul>{links}</ul></details>'
    )


def render_card(card, ratings=False):
    image = ""
    if card.shows_image:
        encoded = b64encode(card.image).decode("ascii")
        image = f'<img alt="{escape(card.alt)}" src="data:{card.mime};base64,{encoded}">'
    description = ""
    if card.description:
        label = "Archival description" if card.archive else "Heritage notes"
        description = f'<p><b>{label}</b><br>{escape(card.description)}</p>'
    scores = ""
    if ratings:
        scores = '<dl class="relic-scores">' + "".join(
            f'<div><dt title="{escape(tip)}">{escape(stat)}</dt><dd>{card.score(stat)}</dd></div>'
            for stat, tip in STATS.items()
        ) + "</dl>"
    st.html(
        f'<article class="relic-portrait">{image}<p class="gallery">{escape(card.category)}</p>'
        f'<h3>{escape(card.name)}</h3><p><b>{escape(card.subject)}</b></p>{description}'
        f'<p><b>Fictional biography</b><br>{escape(card.bio)}</p>'
        f'{render_reference(card)}{render_credits(card)}{scores}</article>'
    )


def show_rules():
    for rule in RULES:
        st.markdown(f"- {rule}")


def show_lobby(deck, tables):
    hero = STATIC / "hero.webp"
    picture = ""
    if hero.exists():
        encoded = b64encode(hero.read_bytes()).decode("ascii")
        picture = (
            f'<img src="data:image/webp;base64,{encoded}" alt="Three portrait cards show a badger '
            'with a quilt, a dame with an illuminated manuscript and a goblin with a painted portrait.">'
        )
    st.html(
        '<section class="relic-hero"><div><small>✦ THE MUSEUM AFTER HOURS</small>'
        '<h1>Relic <em>Ruckus.</em></h1>'
        '<p>Thirty-six oddball curators. Six ways to win a comparison. Pick a stat and see who takes the collection.</p>'
        '<small>36 cards · 6 galleries · 1–3 humans + computer</small>'
        f'</div>{picture}</section>'
    )
    setup, guide = st.columns([1.45, 1], gap="medium")
    with setup, st.container(border=True):
        st.header("Set the table")
        st.write("Share one device. The computer always takes one seat.")
        amount = st.radio("Human players", [1, 2, 3], horizontal=True)
        with st.form("new_match"):
            names = [st.text_input(f"Player {seat} name", max_chars=30) for seat in range(1, amount + 1)]
            if st.form_submit_button("Deal the cards", type="primary"):
                try:
                    game = Game(names, deck.snapshot())
                except ValueError as error:
                    st.error(str(error))
                else:
                    st.query_params["table"] = tables.start(game, st.query_params.get("table"))
                    st.rerun()
    with guide, st.container(border=True):
        st.header("One card. One call.")
        st.markdown(
            "**Pass the device.** Only the leader sees their top card.\n\n"
            "**Call a stat.** The highest score takes the played cards.\n\n"
            "**Play through ties.** Build the pot and keep the same stat."
        )


def table_status(game):
    counts = []
    for player in game.players:
        status = "out" if not player.pile and not game.winners else "cards"
        counts.append(f"<li>{escape(player.name)} <b>{len(player.pile)}</b> {status}</li>")
    counts.append(f"<li>Pot <b>{len(game.pot)}</b> cards</li>")
    line = f"Dealer {escape(game.players[game.dealer].name)}"
    if game.result and game.result.outcome == "tie":
        line += f" · Caller {escape(game.lead_player.name)} · {game.result.stat} carries forward"
    elif not game.winners:
        label = "Next leader" if game.result else "Leader"
        line += f" · {label} {escape(game.lead_player.name)}"
    title = "Match complete" if game.winners else "At the table"
    st.html(
        f'<section class="relic-table" aria-label="Table status"><small>ROUND {game.round_number}</small>'
        f'<h1>{title}</h1><p>{line}</p><ul class="relic-status-list" aria-label="Cards by seat">'
        f'{"".join(counts)}</ul></section>'
    )


def show_game(tables, key, game):
    # Rendering never changes a round. Each button includes the revision of the
    # screen it was drawn on, so a rerun or a repeated click cannot reuse it.
    def turn(label, action, stat=None, *, help_text=None, primary=True, wide=False):
        if st.button(label, key=f"{key}-{game.revision}-{action}-{stat}",
                     type="primary" if primary else "secondary", help=help_text, use_container_width=wide):
            tables.act(key, game.revision, action, stat)
            st.rerun()

    def leave(label):
        if st.button(label, key=f"{key}-leave"):
            tables.close(key)
            del st.query_params["table"]
            st.rerun()

    table_status(game)
    if game.phase == "handoff":
        with st.container(border=True, key="handoff-panel"):
            if game.lead_player.computer:
                title = "The computer leads"
                note = "Reveal the computer’s choice when everyone is ready."
                label = "Reveal choice and result"
            else:
                title = f"Pass the device to {escape(game.lead_player.name)}"
                note = "Only the leader should look at the next screen."
                label = "Reveal my card"
            # Give the private reveal a different target from the result screen's
            # next-round button, even if the handoff renders between two clicks.
            st.html(f'<div class="relic-handoff"><h2>{title}</h2><p>{note}</p></div>')
            turn(label, "reveal")
    elif game.phase == "choice":
        choice, portrait = st.columns([1.12, 1], gap="medium")
        with choice, st.container(border=True):
            st.text(f"Private choice · {game.lead_player.name}")
            st.header("Call one stat")
            st.write("Your choice locks before the other cards are revealed. Highest score wins.")
            for stat, tip in STATS.items():
                turn(f"{stat} · {game.private_card.score(stat)}", "choose", stat,
                     help_text=tip, primary=False, wide=True)
        with portrait:
            render_card(game.private_card)
    else:
        result = game.result
        with st.container(border=True):
            st.caption(f"Public result · {result.stat}")
            if result.outcome == "shared":
                st.header("Shared win")
            elif game.winners:
                st.html(f"<h2>{escape(winners_message(game))} wins the match</h2>")
            elif result.outcome == "tie":
                st.header("The pot grows")
            else:
                st.html(f"<h2>{escape(game.players[result.collector].name)} takes the round</h2>")
            message = result_message(game)
            if result.outcome == "shared":
                message += f" {winners_message(game)} share the match."
            st.html(f"<p>{escape(message)}</p>")
            if game.winners:
                leave("Set up another match")
            else:
                label = f"Continue on {result.stat}" if result.outcome == "tie" else "Next handoff"
                turn(label, "continue")
        for column, play in zip(st.columns(len(result.plays)), result.plays):
            with column:
                name = escape(game.players[play.seat].name)
                role = " · Collector" if play.seat == result.collector else (
                    " · Top score" if play.seat in result.high_seats else ""
                )
                st.html(f'<p><strong>{name} · {play.score}</strong>{role}</p>')
                render_card(game.deck[play.card_id])
    with st.expander("Rules at the table"):
        show_rules()
    if not game.winners:
        with st.expander("End this match"):
            leave("Return to setup")


def edit_form(card):
    values = fields_for(card)
    version = f"{card.id}-{card.revision}"

    def field(name, options=None, multiline=False):
        label = TEXT_FIELDS[name]
        key = f"{version}-{name}"
        if options:
            return st.selectbox(label, options, index=options.index(values[name]), key=key)
        if multiline:
            return st.text_area(label, values[name], key=key)
        return st.text_input(label, values[name], key=key)

    with st.form(f"edit-{version}"):
        st.subheader("Card details")
        for name in ("name", "subject", "category", "heritage", "bio"):
            values[name] = field(
                name, options=CATEGORIES if name == "category" else None,
                multiline=name in {"heritage", "bio"},
            )
        st.markdown("**Fictional ratings**")
        for stat, tip in STATS.items():
            values[stat] = st.number_input(stat, 1, 100, card.score(stat), help=tip, key=f"{version}-{stat}")
        with st.expander("Edit object and media details"):
            st.write("When the record opens the image or recording, you can leave the separate media URL blank.")
            for name, label in REFERENCE_FIELDS.items():
                field_name = f"ref_{name}"
                key = f"{version}-{field_name}"
                if name == "media_kind":
                    options = ("", *MEDIA_KINDS)
                    values[field_name] = st.selectbox(label, options, index=options.index(values[field_name]),
                                                      format_func=lambda item: item or "Choose a media type", key=key)
                elif name == "notes":
                    values[field_name] = st.text_area(label, values[field_name], max_chars=600, key=key)
                else:
                    values[field_name] = st.text_input(label, values[field_name],
                                                       max_chars=2000 if name.endswith("_url") else 600, key=key)
        st.subheader("Portrait and archival text")
        st.write("Use public-domain, CC0 or explicitly licensed assets for archival replacements. Credit the specific image and text separately.")
        values["mode"] = field("mode", options=MODES)
        upload = st.file_uploader("Replacement image", type=["png", "jpg", "jpeg", "webp"],
                                  help="Update the image credit for the uploaded file.", key=f"{version}-image")
        remove = st.checkbox("Remove the stored image", key=f"{version}-remove")
        values["alt"] = field("alt")
        values["archive"] = field("archive", multiline=True)
        for kind, heading in (("image", "Image credit"), ("text", "Archival text credit")):
            st.markdown(f"**{heading}**")
            for name, label in CREDIT_FIELDS.items():
                key = f"{kind}_{name}"
                values[key] = st.text_input(f"{heading} · {label}", values[key], key=f"{version}-{key}")
        if st.form_submit_button("Preview changes", type="primary"):
            st.session_state.pop("draft", None)
            try:
                st.session_state["draft"] = make_draft(
                    card, values, upload=upload.getvalue() if upload else None, remove=remove,
                )
            except ValueError as error:
                st.error(str(error))


def show_editor(deck):
    st.title("Deck editor")
    st.write("Find a card by character, object or gallery. Saved edits appear in new matches in both editions.")
    if "editor_notice" in st.session_state:
        st.success(st.session_state.pop("editor_notice"))
    search, group = st.columns([1.4, 1])
    query = search.text_input("Search the deck")
    category = group.selectbox("Gallery", ("All galleries", *CATEGORIES))
    cards = filter_cards(deck.summaries(), query, category)
    if not cards:
        st.info("No cards match that search.")
        return
    labels = {card["id"]: f"{card['name']} · {card['subject']}" for card in cards}
    card_id = st.selectbox("Card to edit", list(labels), format_func=labels.get)
    card = deck.get(card_id)
    form, preview = st.columns([1.32, 1], gap="medium")
    with form, st.container(border=True):
        edit_form(card)
    with preview:
        draft = st.session_state.get("draft")
        if draft and (draft.id != card.id or draft.revision != card.revision):
            draft = None
            st.session_state.pop("draft", None)
        st.header("Draft preview" if draft else "Saved card")
        if draft and st.button("Save changes", type="primary", key=f"save-{draft.id}-{draft.revision}"):
            try:
                deck.save(draft)
            except ValueError as error:
                st.error(str(error))
            else:
                st.session_state.pop("draft", None)
                st.session_state["editor_notice"] = f"Saved {draft.name}. New matches will use the updated card."
                st.rerun()
        render_card(draft or card, ratings=True)


def main():
    st.set_page_config(page_title="Relic Ruckus", page_icon="✦", layout="wide")
    st.html(STATIC / "streamlit.css")
    deck = get_deck(os.getenv("RELIC_DB_PATH"))
    tables = get_tables()
    page = st.radio("Relic Ruckus navigation", ["Play", "Deck editor", "How to play"], horizontal=True,
                    label_visibility="collapsed")
    if page == "Deck editor":
        show_editor(deck)
    elif page == "How to play":
        st.title("How to play")
        st.write("Enter one to three human names. The computer joins automatically. The deck is shuffled and all 36 cards are dealt evenly. The player to the dealer’s left leads.")
        show_rules()
    else:
        key = st.query_params.get("table")
        game = tables.view(key)
        if game is None:
            show_lobby(deck, tables)
        else:
            show_game(tables, key, game)


if __name__ == "__main__":
    main()
