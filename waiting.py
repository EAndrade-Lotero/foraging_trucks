"""Lobby pages shown while a quorum is forming, and the activity counter.

Every lobby page must call ``consecutive_unpaired_waits``. That counter is
what the short start and the stale-tab check read. A page that does not call
it makes the participant look frozen.
"""

import time

from markupsafe import Markup, escape
from psynet.modular_page import ModularPage, NullControl
from psynet.timeline import Event, PageMaker
from psynet.trial.static import StaticNode, StaticTrial, StaticTrialMaker

from .game_parameters import (
    BASE_GROUP_SIZE,
    MIN_GROUP_SIZE,
    WAITING_TRIAL_TIME_ESTIMATE,
)
from .grouping import GroupRound, Pair, Quorum


class WaitingNode(StaticNode):
    def create_initial_seed(self, experiment, participant):
        # An empty definition is treated as missing, so the chain constructor
        # asks the node for a seed instead of storing {}.
        return {"waiting": True}

    def create_definition_from_seed(self, seed, experiment, participant):
        return dict(seed)


class LobbyWaitingPage(StaticTrial):
    """One lobby page. It advances on its own, and Next also advances it."""

    time_estimate = WAITING_TRIAL_TIME_ESTIMATE

    def show_trial(self, experiment, participant):
        consecutive_unpaired_waits(participant)
        return ModularPage(
            "waiting_trial",
            Markup(_lobby_html(participant)),
            NullControl(),
            show_next_button=True,
            time_estimate=WAITING_TRIAL_TIME_ESTIMATE,
            bot_response="No answer",
            events={
                "autoSubmit": Event(
                    is_triggered_by="trialStart",
                    delay=float(WAITING_TRIAL_TIME_ESTIMATE),
                    once=True,
                    js="psynet.submitResponse()",
                ),
            },
        )


def _waiting_trial_maker(id_, trial_class):
    return StaticTrialMaker(
        id_=id_,
        trial_class=trial_class,
        nodes=[WaitingNode()],
        expected_trials_per_participant=6,
        max_trials_per_participant=99,
        allow_repeated_nodes=True,
    )


lobby_waiting_trial_maker = _waiting_trial_maker("waiting_lobby", LobbyWaitingPage)


def waiting_logic():
    """A fresh lobby page for one barrier.

    ``Barrier.resolve()`` tags the elements it receives with a link back to
    the barrier, so each barrier needs its own page.
    """
    trial_maker = lobby_waiting_trial_maker
    return PageMaker(
        trial_maker.cue_trial, time_estimate=trial_maker.trial_class.time_estimate
    )


def with_waiting_pages(*elts):
    """Run ``elts`` inside the lobby trial maker, so a barrier can cue a lobby page."""
    return lobby_waiting_trial_maker.custom(*elts)


def lobby_waiting_logic():
    """The page shown before the rounds start, and while a player sits a round out."""
    return waiting_logic()


def consecutive_unpaired_waits(participant) -> int:
    """Waiting pages in a row that have not put this participant in a pair.

    A page is counted once. Getting a pair resets the streak, so the next
    lobby page starts again at 1.
    """
    if Pair.current(participant) is not None:
        participant.var.set("unpaired_wait_pages", 0)
        participant.var.set("unpaired_wait_trial_id", None)
        return 0
    trial = getattr(participant, "current_trial", None)
    trial_id = getattr(trial, "id", None)
    last_id = participant.var.get("unpaired_wait_trial_id", None)
    count = int(participant.var.get("unpaired_wait_pages", 0) or 0)
    if trial_id is not None and trial_id == last_id:
        return count
    # A redraw before the trial has an id must not add another page.
    if trial_id is None:
        return count + 1
    count += 1
    participant.var.set("unpaired_wait_pages", count)
    participant.var.set("unpaired_wait_trial_id", trial_id)
    participant.var.set("last_lobby_page_at", time.time())
    return count


def _lobby_html(participant) -> str:
    """How many people are waiting, and whether a round is already going."""
    roster = Quorum.roster()
    waiting = roster["waiting"]
    in_group = []
    for members in roster["groups"].values():
        if participant.id in members:
            in_group = members
            break
    if in_group:
        count = len(in_group)
        count_line = (
            f"{count} player{'s' if count != 1 else ''} in your group "
            f"(the game starts with {BASE_GROUP_SIZE}, or with {MIN_GROUP_SIZE} "
            "if the wait has gone on)."
        )
    else:
        count = len(waiting)
        count_line = (
            f"{count} player{'s' if count != 1 else ''} waiting. "
            f"The game starts when {BASE_GROUP_SIZE} players are here, "
            f"or when at least {MIN_GROUP_SIZE} have been waiting."
        )
    round_index = GroupRound.current(participant)
    started = (
        round_index > 0
        or GroupRound.is_done(participant, 0)
        or GroupRound.others_still_paired(participant, round_index)
    )
    title = "Waiting for a round to begin" if started else "Waiting for other players"
    return (
        f"<h3>{escape(title)}</h3>"
        f"<p>{escape(count_line)}</p>"
        "<p>Keep this page open. It moves on by itself, and you can also click Next. "
        "Each round you are paired with another player in the group. "
        "If the numbers are odd, one player sits that round out.</p>"
    )
