import json
from typing import List

import psynet.experiment
from markupsafe import Markup
from psynet.bot import Bot, BotDriver
from psynet.modular_page import ModularPage, NumberControl, Prompt
from psynet.page import InfoPage, WaitPage
from psynet.participant import Participant
from psynet.sync import GroupBarrier, SimpleGrouper
from psynet.timeline import FailedValidation, PageMaker, Timeline, join
from psynet.trial.static import StaticNode, StaticTrial, StaticTrialMaker

from .foraging import (
    FORAGING_DURATION,
    MAX_PLAYERS,
    MIN_PLAYERS,
    EnableForaging,
    ForagingPage,
)


GROUP_TYPE = "crew"
MAX_FUEL = 20
TUTORIAL_SECONDS = 30
FUEL_SECONDS = 20
SCORE_SECONDS = 15
CONTRACT_SECONDS = 20
BARRIER_MAX_WAIT_SECONDS = 180
BARRIER_EXPECTED_WAIT = 10
TRIAL_TIME_ESTIMATE = (
    TUTORIAL_SECONDS
    + FUEL_SECONDS
    + BARRIER_EXPECTED_WAIT
    + FORAGING_DURATION
    + SCORE_SECONDS
    + CONTRACT_SECONDS
)


START_NODES = [
    StaticNode(
        definition={"payment_per_coin": 2.0, "fuel_price": 0.5},
    ),
    StaticNode(
        definition={"payment_per_coin": 1.0, "fuel_price": 0.25},
    ),
    StaticNode(
        definition={"payment_per_coin": 3.0, "fuel_price": 1.0},
    ),
]


def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def current_contract(trial) -> dict:
    definition = trial.definition or {}
    return {
        "payment_per_coin": _as_float(definition.get("payment_per_coin"), 1.0),
        "fuel_price": _as_float(definition.get("fuel_price"), 0.5),
    }


def latest_accumulated_answers(participant: Participant) -> dict:
    if participant.answer_accumulators:
        return participant.answer_accumulators[-1] or {}
    if isinstance(participant.answer, dict):
        return participant.answer
    return {}


def compute_score(contract: dict, fuel_bought: float, coins_collected: float) -> float:
    return coins_collected * contract["payment_per_coin"] - fuel_bought * contract["fuel_price"]


class BoundedNumberControl(NumberControl):
    def __init__(self, min_value: float, max_value: float, bot_response=5, **kwargs):
        super().__init__(bot_response=bot_response, **kwargs)
        self.min_value = min_value
        self.max_value = max_value

    def validate(self, response, **kwargs):
        failed = super().validate(response, **kwargs)
        if failed is not None:
            return failed
        value = _as_float(response.answer)
        if value < self.min_value or value > self.max_value:
            return FailedValidation(
                f"Enter a number between {self.min_value} and {self.max_value}."
            )
        return None

    def format_answer(self, raw_answer, **kwargs):
        return _as_float(raw_answer)


def tutorial_page(contract: dict) -> InfoPage:
    content = Markup(
        f"""
        <h3>How this round works</h3>
        <p>You are playing with a crew. Each round has four steps after this tutorial:</p>
        <ol>
            <li><strong>Buy fuel</strong> for your truck (0 to {MAX_FUEL} litres).</li>
            <li><strong>Collect coins</strong> on a shared {10}&times;{10} board. Use arrow keys or WASD.</li>
            <li><strong>See your score</strong> according to the current contract.</li>
            <li><strong>Propose a new contract</strong> for later rounds.</li>
        </ol>
        <p>The current contract pays <strong>{contract["payment_per_coin"]}</strong> per coin
        and charges <strong>{contract["fuel_price"]}</strong> per litre of fuel.</p>
        <p>Score = coins collected × payment per coin − fuel bought × fuel price.</p>
        """
    )
    return InfoPage(content, time_estimate=TUTORIAL_SECONDS)


def buy_fuel_page(contract: dict) -> ModularPage:
    prompt = Markup(
        f"""
        <h3>Buy fuel</h3>
        <p>How many litres of fuel do you want to buy for this round? (0–{MAX_FUEL})</p>
        <p>Each litre costs <strong>{contract["fuel_price"]}</strong> under the current contract.</p>
        """
    )
    return ModularPage(
        "buy_fuel",
        Prompt(prompt),
        BoundedNumberControl(min_value=0, max_value=MAX_FUEL, bot_response=5),
        time_estimate=FUEL_SECONDS,
    )


def score_page(participant: Participant, contract: dict) -> InfoPage:
    answers = latest_accumulated_answers(participant)
    fuel_bought = _as_float(answers.get("buy_fuel"), 0)
    foraging = answers.get("foraging_page") or {}
    if not isinstance(foraging, dict):
        foraging = {}
    coins_collected = _as_float(foraging.get("coins_collected"), 0)
    score = compute_score(contract, fuel_bought, coins_collected)
    content = Markup(
        f"""
        <h3>Round score</h3>
        <p>Current contract: <strong>{contract["payment_per_coin"]}</strong> per coin,
        <strong>{contract["fuel_price"]}</strong> per litre of fuel.</p>
        <ul>
            <li>Coins collected: <strong>{int(coins_collected)}</strong></li>
            <li>Fuel bought: <strong>{fuel_bought}</strong> litres</li>
            <li>Score: <strong>{score:.2f}</strong></li>
        </ul>
        <p>Score = {int(coins_collected)} × {contract["payment_per_coin"]}
        − {fuel_bought} × {contract["fuel_price"]}.</p>
        """
    )
    return InfoPage(content, time_estimate=SCORE_SECONDS)


def propose_contract_page(contract: dict) -> ModularPage:
    prompt = Markup(
        f"""
        <h3>Propose a new contract</h3>
        <p>The current payment per coin is <strong>{contract["payment_per_coin"]}</strong>.</p>
        <p>Propose a new payment per coin for future rounds (0 to 10).</p>
        <p>Fuel will still be priced at <strong>{contract["fuel_price"]}</strong> per litre
        unless you change that in later versions of this experiment.</p>
        """
    )
    return ModularPage(
        "propose_contract",
        Prompt(prompt),
        BoundedNumberControl(min_value=0, max_value=10, bot_response=2),
        time_estimate=CONTRACT_SECONDS,
    )


class ForagingTrucksTrial(StaticTrial):
    time_estimate = TRIAL_TIME_ESTIMATE
    accumulate_answers = True

    def show_trial(self, experiment, participant):
        contract = current_contract(self)
        return join(
            tutorial_page(contract),
            buy_fuel_page(contract),
            GroupBarrier(
                id_="foraging_round_start",
                group_type=GROUP_TYPE,
                waiting_logic=WaitPage(
                    wait_time=1.0,
                    content="Waiting for the rest of your crew to finish buying fuel...",
                    # Without this the wait pages would add empty entries to the
                    # trial's accumulated answers.
                    save_answer=False,
                ),
                waiting_logic_expected_repetitions=BARRIER_EXPECTED_WAIT,
                max_wait_time=BARRIER_MAX_WAIT_SECONDS,
            ),
            ForagingPage(participant, round_id=self.node_id),
            PageMaker(
                lambda participant: score_page(participant, contract),
                time_estimate=SCORE_SECONDS,
            ),
            propose_contract_page(contract),
        )


trial_maker = StaticTrialMaker(
    id_="foraging_trucks",
    trial_class=ForagingTrucksTrial,
    nodes=START_NODES,
    expected_trials_per_participant=1,
    max_trials_per_participant=1,
    recruit_mode="n_participants",
    target_n_participants=20,
    sync_group_type=GROUP_TYPE,
)


class Exp(psynet.experiment.Experiment):
    label = "Foraging trucks"

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
                    EnableForaging.remove_participant(participant_id, self)
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
                """
                <h3>Welcome</h3>
                <p>You will be grouped with other players, buy fuel for your truck,
                collect coins on a shared board, receive a score under a contract,
                and propose a new contract.</p>
                <p>Please wait on the next screen until enough players have joined.</p>
                """
            ),
            time_estimate=10,
        ),
        SimpleGrouper(
            GROUP_TYPE,
            initial_group_size=MIN_PLAYERS,
            max_group_size=MAX_PLAYERS,
            min_group_size=MIN_PLAYERS,
            join_existing_groups=True,
            max_wait_time=120,
        ),
        trial_maker,
        InfoPage(
            "Thank you for playing. You can close this window.",
            time_estimate=5,
        ),
    )

    test_n_bots = 2

    def test_serial_run_bots(self, bots: List[BotDriver]):
        # The bots have to advance in lockstep, otherwise the first bot would sit at
        # the grouper and at the foraging barrier until it timed out.
        max_pages = 100
        for _ in range(max_pages):
            working = [bot for bot in bots if bot.is_working]
            if not working:
                break
            for bot in working:
                bot.take_page()
        else:
            raise AssertionError("Bots did not finish the experiment in time.")

    def test_check_bot(self, bot: Bot, **kwargs):
        assert not bot.failed
