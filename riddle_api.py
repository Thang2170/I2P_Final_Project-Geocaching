"""Riddle chains: make one, follow one, and the bonus for finishing (owner: B). Rules: riddles.py.

- GET    /riddles                 the page
- GET    /api/riddles             every chain, with what YOU can see of it
- POST   /api/riddles             make a chain {"title", "steps": [{"treasure_id", "clue"}, ...]}
- DELETE /api/riddles/<id>        delete your own chain
pay_finished_chains() is called by the treasure claim (coin_api.py) right after a find is paid.
"""

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy.exc import IntegrityError

from auth_api import current_user
from models import ChainBonus, CoinTransaction, RiddleChain, RiddleStep, Treasure, db
from riddles import CHAIN_BONUS, CURRENT, FOUND, is_complete, parse_chain, step_states

riddle_api = Blueprint("riddle_api", __name__)

BONUS_REASON = "riddle_chain"


def _found_ids(user_id):
    from coin_api import found_treasure_ids  # here, not at the top: coin_api imports this file
    return found_treasure_ids(user_id)


def _paid_chain_ids(user_id):
    return set(db.session.execute(db.select(ChainBonus.chain_id).where(ChainBonus.user_id == user_id)).scalars())


def _chain_dict(chain, me, found, paid):
    ids = [s.treasure_id for s in chain.steps]
    states = step_states(ids, found)
    steps = []
    for step, state in zip(chain.steps, states):
        item = {"n": step.position, "state": state}
        if state in (FOUND, CURRENT):  # a locked riddle never leaves the server
            item["clue"] = step.clue
        if state == FOUND:
            item["treasure"] = step.treasure.name
            item["treasure_id"] = step.treasure_id
        steps.append(item)
    return {
        "id": chain.id,
        "title": chain.title,
        "creator": chain.creator.username,
        "mine": chain.creator_id == me.id,
        "steps": steps,
        "done": states.count(FOUND),
        "total": len(states),
        "complete": chain.id in paid,
        "bonus": CHAIN_BONUS,
    }


@riddle_api.route("/riddles")
def riddles_page():
    return render_template("riddles.html")


@riddle_api.route("/api/riddles")
def list_chains():
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    found, paid = _found_ids(me.id), _paid_chain_ids(me.id)
    chains = db.session.execute(db.select(RiddleChain).order_by(RiddleChain.id.desc())).scalars().all()
    # Treasures you can put in a chain of your own (the picker on the page).
    treasures = db.session.execute(db.select(Treasure.id, Treasure.name).order_by(Treasure.name)).all()
    return jsonify(chains=[_chain_dict(c, me, found, paid) for c in chains],
                   treasures=[{"id": t.id, "name": t.name} for t in treasures])


@riddle_api.route("/api/riddles", methods=["POST"])
def make_chain():
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    ids = db.session.execute(db.select(Treasure.id)).scalars().all()
    try:
        title, steps = parse_chain(request.get_json(silent=True), ids)
    except ValueError as err:
        return jsonify(error=str(err)), 400
    chain = RiddleChain(title=title, creator_id=me.id)
    chain.steps = [RiddleStep(position=n, treasure_id=tid, clue=clue)
                   for n, (tid, clue) in enumerate(steps, start=1)]
    db.session.add(chain)
    db.session.commit()
    return jsonify(_chain_dict(chain, me, _found_ids(me.id), _paid_chain_ids(me.id))), 201


@riddle_api.route("/api/riddles/<int:chain_id>", methods=["DELETE"])
def delete_chain(chain_id):
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    chain = db.session.get(RiddleChain, chain_id)
    if chain is None:
        return jsonify(error="No such chain"), 404
    if chain.creator_id != me.id:
        return jsonify(error="You can only delete your own chains"), 403
    db.session.execute(db.delete(ChainBonus).where(ChainBonus.chain_id == chain.id))
    db.session.delete(chain)
    db.session.commit()
    return jsonify(ok=True)


def pay_finished_chains(user_id, treasure_id):
    """After a find: pay the bonus for every chain with this treasure that is now complete.

    Returns [{"title": .., "bonus": ..}] for the chains just finished (usually empty).
    """
    chain_ids = db.session.execute(db.select(RiddleStep.chain_id).where(
        RiddleStep.treasure_id == treasure_id).distinct()).scalars().all()
    if not chain_ids:
        return []
    found, paid = _found_ids(user_id), _paid_chain_ids(user_id)
    finished = []
    for chain in db.session.execute(db.select(RiddleChain).where(RiddleChain.id.in_(chain_ids))).scalars():
        if chain.id in paid or not is_complete([s.treasure_id for s in chain.steps], found):
            continue
        db.session.add(ChainBonus(user_id=user_id, chain_id=chain.id))
        db.session.add(CoinTransaction(user_id=user_id, amount=CHAIN_BONUS, reason=BONUS_REASON))
        try:
            db.session.commit()
        except IntegrityError:  # a double tap already paid it
            db.session.rollback()
            continue
        finished.append({"title": chain.title, "bonus": CHAIN_BONUS})
    return finished
