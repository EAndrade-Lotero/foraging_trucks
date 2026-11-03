import json
import os
import time
from typing import List

import psynet.experiment
from markupsafe import Markup
from psynet.bot import Bot, BotDriver
from psynet.page import InfoPage
from psynet.timeline import PageMaker, Timeline

from .foraging import EnableForaging, patch_dallinger_sockets
from .foraging_trucks import summary_page, trial_maker, tutorial_page
from .game_parameters import (
    BASE_GROUP_SIZE,
    INCLUDE_TUTORIAL,
    MIN_GROUP_SIZE,
    N_ROUNDS,
)
from .grouping import (
    CompletedEndLogic,
    ForagingQuorumGrouper,
    Quorum,
    QuorumWaitEndLogic,
)
from .tutorial import buying_moves_tutorial, contract_tutorial, moving_tutorial
from .waiting import with_waiting_pages


class Exp(psynet.experiment.Experiment):
    label = "Foraging trucks"
    css_links = ["static/foraging.css"]
    config = {
        "initial_recruitment_size": BASE_GROUP_SIZE,
        # Recruiters show this title. The pre-launch check rejects an empty one.
        "title": "Foraging trucks",
    }

    def __init__(self, *args, **kwargs):
        patch_dallinger_sockets()  # deferred from import time, see foraging.py
        super().__init__(*args, **kwargs)

    def receive_message(
        self, message, channel_name=None, participant=None, node=None, receive_time=None
    ):
        if channel_name == "dallinger_control":
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                data = {}
            if data.get("type") == "websocket" and data.get("event") == "disconnected":
                participant_id = data.get("client", {}).get("participant_id")
                if participant_id is not None:
                    EnableForaging.mark_disconnected(participant_id, self)
            return

        super().receive_message(
            message,
            channel_name=channel_name,
            participant=participant,
            node=node,
            receive_time=receive_time,
        )

    timeline = Timeline(
        EnableForaging(),
        InfoPage(
            Markup(
                f"""
                <h3>Welcome</h3>
                <p>In this game you collect food with other players. Each round you are
                paired with one of them.</p>
                <ul>
                    <li><strong>Your partner is a real person</strong> playing at the same
                    time as you."""
                + (" In the practice tutorials the computer plays your partner, and the "
                   "practice does not count." if INCLUDE_TUTORIAL else "")
                + f"""</li>
                    <li>The game waits until {BASE_GROUP_SIZE} players are ready. It can
                    start earlier, once {MIN_GROUP_SIZE} players have been waiting.</li>
                    <li>Each round the group is paired at random. If the numbers are odd,
                    one player sits that round out and rejoins on the next round.</li>
                </ul>
                """
                + (
                    """
                <p>First, three short tutorials show you how to play. Then you wait
                for the group.</p>
                """
                    if INCLUDE_TUTORIAL
                    else """
                <p>Next you wait for the group, and then the game starts.</p>
                """
                )
            ),
            time_estimate=10,
        ),
        *(
            [
                tutorial_page(),
                buying_moves_tutorial(),
                moving_tutorial(),
                contract_tutorial(),
            ]
            if INCLUDE_TUTORIAL
            else []
        ),
        with_waiting_pages(
            ForagingQuorumGrouper.build(
                BASE_GROUP_SIZE,
                Quorum.BARRIER_ID,
            ),
            trial_maker,
            PageMaker(summary_page, time_estimate=10),
        ),
        successful_end=CompletedEndLogic(),
        unsuccessful_end=QuorumWaitEndLogic(),
    )

    # Two bots still exercise the game: the lobby short-starts at MIN_GROUP_SIZE.
    test_n_bots = MIN_GROUP_SIZE

    def test_serial_run_bots(self, bots: List[BotDriver]):
        # The bots have to advance in lockstep, otherwise the first bot would sit at
        # the grouper and at the barriers until it timed out.
        # FORAGING_TEST_DROPOUT=n: the second bot stops after n pages (closes the tab), and the
        # first must be released after PARTNER_TIMEOUT_SECONDS and finish the game alone.
        dropout = int(os.environ.get("FORAGING_TEST_DROPOUT", "0"))
        pages = [0] * len(bots)
        deadline = time.time() + 900
        while time.time() < deadline:
            working = [
                (i, bot) for i, bot in enumerate(bots)
                if bot.is_working and not (dropout and i == 1 and pages[i] >= dropout)
            ]
            if not working:
                break
            for i, bot in working:
                bot.take_page()
                pages[i] += 1
            if dropout:
                time.sleep(0.2)
        else:
            raise AssertionError("Bots did not finish the experiment in time.")

    def test_check_bots(self, bots: List[Bot]):
        super().test_check_bots(bots)
        if os.environ.get("FORAGING_TEST_DROPOUT"):
            assert any(b.var.get("partner_left", False) for b in bots), \
                "the bot that stayed was never told its partner left"

    def test_check_bot(self, bot: Bot, **kwargs):
        assert not bot.failed
        n = len(bot.var.get("scores", {}))
        assert n <= N_ROUNDS
        assert len(bot.var.get("results", [])) == n
        if not os.environ.get("FORAGING_TEST_DROPOUT"):  # the bot that leaves may have none
            assert n >= 1
