"""Presenter mode for the final demo (owner: B). The run sheet lives in presenter.py.

    GET  /present                       the start page: the run sheet and a Start button
    POST /api/present {"action": ...}   start / next / back / stop -> {"step", "url"}

Which step you are on is kept in the login session (nothing is saved in the database).
While presenting, every page that includes the top bar shows the panel (_presenter.html):
the context processor below gives each page the current step as `presenter`.

app.py registers it like the other Blueprints:

    from presenter_api import presenter_api
    app.register_blueprint(presenter_api)
"""

from flask import Blueprint, jsonify, render_template, request, session

from presenter import move, page_after, panel, parse_action, run_sheet, who_text

presenter_api = Blueprint("presenter_api", __name__)

KEY = "present_step"


def current_step():
    index = session.get(KEY)
    return index if isinstance(index, int) else None


@presenter_api.app_context_processor
def presenter_panel():
    """Every page gets `presenter`: the current step's panel, or None when not presenting."""
    return {"presenter": panel(current_step())}


@presenter_api.route("/present")
def present_page():
    return render_template("present.html", steps=run_sheet(), who=who_text(),
                           done=request.args.get("done") is not None)


@presenter_api.route("/api/present", methods=["POST"])
def present():
    try:
        action = parse_action(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    index = move(current_step(), action)
    if index is None:
        session.pop(KEY, None)
    else:
        session[KEY] = index
    return jsonify(step=panel(index), url=page_after(index))
