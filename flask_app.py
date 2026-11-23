"""Run locally with python -m flask --app flask_app run --port 5050."""
from base64 import b64encode
from secrets import compare_digest, token_hex

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

from relic.cards import CATEGORIES, MAX_IMAGE_BYTES, MODES, STATS
from relic.copy import result_message, winners_message
from relic.database import Deck
from relic.editor import CREDIT_FIELDS, TEXT_FIELDS, fields_for, filter_cards, make_draft
from relic.references import MEDIA_KINDS, REFERENCE_FIELDS, is_source_link
from relic.room import Tables
from relic.rules import Game, RULES


def image_uri(card):
    return f"data:{card.mime};base64,{b64encode(card.image).decode('ascii')}"


def create_app(database_path=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=token_hex(32), MAX_CONTENT_LENGTH=MAX_IMAGE_BYTES + 64 * 1024,
        SESSION_COOKIE_SAMESITE="Strict",
    )
    deck = Deck(database_path)
    tables = Tables()
    drafts = {}

    @app.context_processor
    def presentation():
        if "form_token" not in session:
            session["form_token"] = token_hex(24)
        return dict(stats=STATS, rules=RULES, categories=CATEGORIES, modes=MODES,
                    image_uri=image_uri, is_source_link=is_source_link,
                    form_token=session["form_token"])

    @app.before_request
    def check_form():
        if request.method == "POST":
            token = session.get("form_token", "")
            submitted = request.form.get("form_token", "")
            if not token or not compare_digest(submitted.encode(), token.encode()):
                abort(400, "This form has expired. Reload the page and try again.")

    @app.after_request
    def keep_private(response):
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(413)
    def too_large(_):
        return render_template("problem.html", message="This upload is too large. Choose an image up to 5 MB."), 413

    @app.get("/")
    def play():
        table_key = session.get("table")
        game = tables.view(table_key)
        if game is None:
            return render_template("home.html", names=("",), active="play")
        return render_template(
            "game.html", game=game, table_key=table_key, active="play",
            message=result_message(game) if game.result else "",
            winners=winners_message(game) if game.winners else "",
        )

    @app.post("/start")
    def start():
        amount = request.form.get("humans", 1, type=int)
        names = [request.form.get(f"player_{seat}", "") for seat in range(1, max(1, min(3, amount)) + 1)]
        try:
            if not 1 <= amount <= 3:
                raise ValueError("Choose one to three humans.")
            game = Game(names, deck.snapshot())
        except ValueError as error:
            return render_template("home.html", names=names, error=str(error), active="play"), 400
        session["table"] = tables.start(game, session.get("table"))
        return redirect(url_for("play"), code=303)

    @app.post("/turn")
    def turn():
        table_key = session.get("table")
        if table_key and request.form.get("table_key") == table_key:
            tables.act(
                table_key, request.form.get("revision", -1, type=int),
                request.form.get("action"), request.form.get("stat"),
            )
        # Refresh after a POST repeats only the GET in the redirect.
        return redirect(url_for("play"), code=303)

    @app.post("/leave")
    def leave():
        if request.form.get("table_key") == session.get("table"):
            tables.close(session.pop("table", None))
        return redirect(url_for("play"), code=303)

    @app.get("/rules")
    def how_to_play():
        return render_template("rules.html", active="rules")

    @app.get("/editor")
    def editor():
        query = request.args.get("q", "")[:120]
        category = request.args.get("category", "All galleries")
        cards = filter_cards(deck.summaries(), query, category)
        return render_template("editor.html", cards=cards, query=query, category=category, active="editor")

    def edit_page(card, values, *, error=None, draft=None, draft_token=None):
        return render_template(
            "edit_card.html", card=card, values=values, fields=TEXT_FIELDS, credit_fields=CREDIT_FIELDS,
            reference_fields=REFERENCE_FIELDS, media_kinds=MEDIA_KINDS,
            error=error, preview=draft, draft_token=draft_token, active="editor",
        )

    @app.route("/editor/<card_id>", methods=["GET", "POST"])
    def edit_card(card_id):
        card = deck.get(card_id)
        if card is None:
            abort(404)
        if request.method == "GET":
            return edit_page(card, fields_for(card))
        owner = session["form_token"]
        if request.form.get("action") == "save":
            saved = drafts.get(owner)
            if not saved or saved[0] != request.form.get("draft_token") or saved[1].id != card_id:
                return edit_page(card, fields_for(card), error="This preview expired. Preview the card again.")
            draft = saved[1]
            try:
                deck.save(draft)
            except ValueError as error:
                return edit_page(card, fields_for(card), error=str(error))
            drafts.pop(owner, None)
            flash(f"Saved {draft.name}. New matches will use the updated card.")
            return redirect(url_for("edit_card", card_id=card_id), code=303)

        values = request.form.to_dict()
        try:
            if request.form.get("revision", -1, type=int) != card.revision:
                raise ValueError("This card changed while you were editing. Review the current fields and apply your edits again.")
            upload = request.files.get("image")
            retained = drafts.get(owner)
            earlier = retained[1] if retained and retained[0] == values.get("draft_token") else None
            if earlier and earlier.id == card_id and earlier.revision == card.revision:
                # Re-previewing a draft can reuse its uploaded image without another upload.
                card_for_draft = earlier
            else:
                card_for_draft = card
            draft = make_draft(
                card_for_draft, values,
                upload=upload.read() if upload and upload.filename else None, remove="remove" in values,
            )
            draft_token = token_hex(16)
            drafts[owner] = (draft_token, draft)
        except ValueError as error:
            if request.form.get("revision", -1, type=int) != card.revision:
                values = fields_for(card)
            return edit_page(card, values, error=str(error)), 400
        return edit_page(card, fields_for(draft), draft=draft, draft_token=draft_token)

    return app
