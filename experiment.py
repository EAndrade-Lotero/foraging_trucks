import json
from typing import List

import psynet.experiment
from markupsafe import Markup
from psynet.bot import Bot, BotDriver
from psynet.modular_page import ModularPage, Prompt, SliderControl
from psynet.page import InfoPage, WaitPage
from psynet.participant import Participant
from psynet.sync import GroupBarrier, SimpleGrouper
from psynet.timeline import CodeBlock, PageMaker, Timeline, join
from psynet.trial.static import StaticNode, StaticTrial, StaticTrialMaker

from .foraging import (
    FORAGING_DURATION,
    MAX_MOVES,
    MIN_PLAYERS,
    MOVE_PRICE,
    ROUND_TERRAINS,
    EnableForaging,
    ForagingPage,
    last_valid_answer,
)
from .game_parameters import INCLUDE_TUTORIAL
from .tutorial import (
    CONTRACT_ENDS,
    buying_moves_tutorial,
    contract_tutorial,
    moving_tutorial,
    slider_frame,
)


GROUP_TYPE = "crew"
N_ROUNDS = 2

# Demo economy (not final), in points, on slide 15's scale: a collected coin is worth
# COIN_POINTS, the round's food costs one coin (FIXED_COST), 15 moves cost three coins
# (MOVE_PRICE in foraging.py) and players start with four coins (START_BALANCE).
# COIN_POINTS is a multiple of 20 so that, with 10% contract steps, every part of the split
# (kept and pooled) is a whole number. The balance carries over rounds; nobody is eliminated
# yet (open question: a threshold or a negative balance) and moves can always be bought.
COIN_POINTS = 20
FIXED_COST = COIN_POINTS  # food, one coin per round (slide 15)
START_BALANCE = 4 * COIN_POINTS
START_CONTRACT = 0.0  # 0 = commission (keep your coins), 1 = wages (equal split)

TUTORIAL_SECONDS = 30
MOVES_SECONDS = 20
SCORE_SECONDS = 20
CONTRACT_SECONDS = 20
BARRIER_MAX_WAIT_SECONDS = 180
BARRIER_EXPECTED_WAIT = 10
TRIAL_TIME_ESTIMATE = (
    MOVES_SECONDS
    + BARRIER_EXPECTED_WAIT
    + FORAGING_DURATION
    + SCORE_SECONDS
    + CONTRACT_SECONDS
)


# The node only identifies the round slot; the contract lives in the sync group,
# because it changes with the players' proposals.
START_NODES = [StaticNode(definition={"slot": i}) for i in range(N_ROUNDS)]


def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def crew(participant: Participant):
    return participant.active_sync_groups[GROUP_TYPE]


def current_contract(participant: Participant) -> float:
    return _as_float(crew(participant).var.get("contract", START_CONTRACT))


def split_parts(contract: float, own: int, partner: int) -> tuple:
    """Commission-wages rule (slides 11-13), in points.

    Commission: each player keeps (1 - contract) of their own points. Wages: the rest of
    both players' points goes into a common pot that is split equally.
    Returns (kept, half_of_pot, total) for the first player; all whole numbers.
    """
    kept = round((1 - contract) * own)
    half_pot = round(contract * (own + partner) / 2)
    return kept, half_pot, kept + half_pot


def split(contract: float, own: int, partner: int) -> int:
    return split_parts(contract, own, partner)[2]


def split_table(contract: float, own: int, partner: int, you: str = "You") -> str:
    """The division of the points, step by step, for both players."""
    k1, h1, t1 = split_parts(contract, own, partner)
    k2, h2, t2 = split_parts(contract, partner, own)
    c, w = round(100 * (1 - contract)), round(100 * contract)
    return f"""
        <table class="points-table">
            <tr><th></th><th class="num">{you}</th><th class="num">Partner</th></tr>
            <tr><td>Points from coins collected</td><td class="num">{own}</td><td class="num">{partner}</td></tr>
            <tr><td><strong>Commission {c}%</strong>
                <span class="note">each keeps {c}% of their own points</span></td>
                <td class="num">{k1}</td><td class="num">{k2}</td></tr>
            <tr><td><strong>Wages {w}%</strong>
                <span class="note">the other {w}% of both: a pot of {h1 + h2} points, split equally</span></td>
                <td class="num">+ {h1}</td><td class="num">+ {h2}</td></tr>
            <tr class="total"><td>Share</td><td class="num">{t1}</td><td class="num">{t2}</td></tr>
        </table>
    """


# The same rule and table in JavaScript, for the live slider previews.
SPLIT_JS = """
function splitParts(w, own, partner) {
    var kept = Math.round((1 - w) * own), halfPot = Math.round(w * (own + partner) / 2);
    return [kept, halfPot, kept + halfPot];
}
function split(w, own, partner) { return splitParts(w, own, partner)[2]; }
function splitTable(w, own, partner, you) {
    var a = splitParts(w, own, partner), b = splitParts(w, partner, own);
    var c = Math.round(100 * (1 - w)), p = Math.round(100 * w), n = '<td class="num">';
    return '<table class="points-table">'
        + '<tr><th></th><th class="num">' + (you || "You") + '</th><th class="num">Partner</th></tr>'
        + "<tr><td>Points from coins collected</td>" + n + own + "</td>" + n + partner + "</td></tr>"
        + "<tr><td><strong>Commission " + c + '%</strong><span class="note">each keeps ' + c
        + "% of their own points</span></td>" + n + a[0] + "</td>" + n + b[0] + "</td></tr>"
        + "<tr><td><strong>Wages " + p + '%</strong><span class="note">the other ' + p
        + "% of both: a pot of " + (a[1] + b[1]) + " points, split equally</span></td>"
        + n + "+ " + a[1] + "</td>" + n + "+ " + b[1] + "</td></tr>"
        + '<tr class="total"><td>Share</td>' + n + a[2] + "</td>" + n + b[2] + "</td></tr></table>";
}
"""


def contract_label(contract: float) -> str:
    return f"{round(100 * (1 - contract))}% commission / {round(100 * contract)}% wages"


def coins_collected(participant: Participant) -> int:
    answer = last_valid_answer(participant, "foraging_page")
    return int(answer.get("coins_collected", 0)) if isinstance(answer, dict) else 0


def moves_bought(participant: Participant) -> int:
    return round(_as_float(last_valid_answer(participant, "buy_moves")))


def moves_cost(moves: int) -> int:
    return moves * MOVE_PRICE


def partner_of(participant: Participant):
    others = [p for p in crew(participant).participants if p.id != participant.id]
    return others[0] if others else None


def average_proposals(group, participants, participant, barrier):
    """Runs when both players have proposed: the next contract is their average."""
    proposals = [
        _as_float(last_valid_answer(p, "propose_contract"), None) for p in participants
    ]
    proposals = [p for p in proposals if p is not None]
    if proposals:
        # Rounded to the slider's 10% steps, so every split stays in whole points.
        average = sum(proposals) / len(proposals)
        group.var.set("contract", int(average * 10 + 0.5) / 10)


def slider_preview(slider_id: str, output_id: str, js_body: str) -> str:
    """Live text next to a slider; `v` is the current slider value.

    Runs on trialConstruct because the PsyNet slider control is rendered after the prompt.
    """
    return f"""
        <div id="{output_id}" class="live-value"></div>
        <script>
        {SPLIT_JS}
        psynet.trial.onEvent("trialConstruct", function () {{
            var slider = document.getElementById("{slider_id}");
            var out = document.getElementById("{output_id}");
            function render() {{
                var v = parseFloat(slider.value);
                {js_body}
            }}
            slider.addEventListener("input", render);
            render();
        }});
        </script>
    """


CONTRACT_STEPS = 11  # 0%, 10%, ..., 100% wages
MOVE_STEPS = MAX_MOVES + 1


def wait_page(text: str) -> WaitPage:
    # Without save_answer=False the wait pages would add empty entries to the
    # trial's accumulated answers.
    return WaitPage(wait_time=1.0, content=text, save_answer=False)


def crew_barrier(id_: str, text: str, on_release=None) -> GroupBarrier:
    return GroupBarrier(
        id_=id_,
        group_type=GROUP_TYPE,
        waiting_logic=wait_page(text),
        waiting_logic_expected_repetitions=BARRIER_EXPECTED_WAIT,
        max_wait_time=BARRIER_MAX_WAIT_SECONDS,
        on_release=on_release,
    )


def tutorial_page() -> InfoPage:
    return InfoPage(
        Markup(
            f"""
            <h3>How the game works</h3>
            <p>You and a partner each move a pac-man and collect coins. Each coin is worth
            <strong>{COIN_POINTS} points</strong>. You start with <strong>{START_BALANCE} points</strong>
            and play <strong>{N_ROUNDS} rounds</strong>, each on a new terrain; your points carry over
            from round to round. Each round:</p>
            <ol>
                <li><strong>Buy moves</strong>: 0 to {MAX_MOVES} moves, {MOVE_PRICE} points each.
                    With no moves left you stop.</li>
                <li><strong>Collect coins</strong> for {FORAGING_DURATION} seconds with the arrow keys or WASD.</li>
                <li><strong>Split the points</strong> with the current contract, then pay for your moves
                    and {FIXED_COST} points of food.</li>
                <li><strong>Propose a new contract</strong> for the next round.</li>
            </ol>
            """
        ),
        time_estimate=TUTORIAL_SECONDS,
    )


def coins(n: int) -> str:
    return f"{n} coin" if n == 1 else f"{n} coins"


def balance(participant: Participant) -> int:
    """Points carried over: the starting points plus every finished round."""
    return START_BALANCE + sum(participant.var.get("scores", {}).values())


def buy_moves_page(participant: Participant, round_index: int) -> ModularPage:
    preview = slider_preview(
        "moves-slider",
        "moves-output",
        f"""
        out.innerHTML = "<strong>" + v + " moves</strong> cost <strong>" + (v * {MOVE_PRICE}) + " points</strong>";
        """,
    )
    prompt = Markup(
        f"""
        <h3>Round {round_index + 1} of {N_ROUNDS}: buy moves</h3>
        <p>You have <strong>{balance(participant)} points</strong>.</p>
        <p><strong>How many moves do you want to buy?</strong> Each move costs {MOVE_PRICE} points.
        Each coin you collect is worth {COIN_POINTS} points. You cannot buy more moves during the round.</p>
        <p>This round also costs {FIXED_COST} points of food. Current contract:
        <strong>{contract_label(current_contract(participant))}</strong>.</p>
        {preview}
        {slider_frame("moves-slider", "0 moves", f"{MAX_MOVES} moves", MOVE_STEPS, below="moves-output")}
        """
    )
    return ModularPage(
        "buy_moves",
        Prompt(prompt),
        SliderControl(
            start_value=5,
            min_value=0,
            max_value=MAX_MOVES,
            n_steps=MOVE_STEPS,  # 0, 1, ..., 15 moves
            slider_id="moves-slider",
            minimal_interactions=1,
            bot_response=8,
        ),
        time_estimate=MOVES_SECONDS,
    )


def round_result(participant: Participant) -> dict:
    contract = current_contract(participant)
    partner = partner_of(participant)
    own = coins_collected(participant) * COIN_POINTS
    other = (coins_collected(partner) if partner else 0) * COIN_POINTS
    moves = moves_bought(participant)
    spent = moves_cost(moves)
    share = split(contract, own, other)
    return dict(
        contract=contract, own=own, other=other, share=share,
        moves=moves, spent=spent, score=share - spent - FIXED_COST,
    )


def store_score(participant: Participant, round_index: int):
    scores = participant.var.get("scores", {})
    scores[str(round_index + 1)] = round_result(participant)["score"]
    participant.var.set("scores", scores)


def score_page(participant: Participant) -> InfoPage:
    r = round_result(participant)
    contract, own, other = r["contract"], r["own"], r["other"]
    share, moves, spent, score = r["share"], r["moves"], r["spent"], r["score"]
    after = balance(participant)  # the score is already stored
    return InfoPage(
        Markup(
            f"""
            <h3>You earned {score} points this round</h3>
            <p>You collected <strong>{coins(own // COIN_POINTS)}</strong> and your partner collected
            <strong>{coins(other // COIN_POINTS)}</strong>. Each coin is worth {COIN_POINTS} points.
            Contract: <strong>{contract_label(contract)}</strong>.</p>
            {split_table(contract, own, other)}
            <table class="points-table">
                <tr><td>Your share</td><td class="num">{share}</td></tr>
                <tr><td>Moves ({moves} × {MOVE_PRICE})</td><td class="num">− {spent}</td></tr>
                <tr><td>Food</td><td class="num">− {FIXED_COST}</td></tr>
                <tr class="total"><td>You earned this round</td><td class="num">{score}</td></tr>
                <tr><td>Your points</td><td class="num">{after - score} → <strong>{after}</strong></td></tr>
            </table>
            """
        ),
        time_estimate=SCORE_SECONDS,
    )


def propose_contract_page(participant: Participant) -> ModularPage:
    contract = current_contract(participant)
    partner = partner_of(participant)
    own = coins_collected(participant) * COIN_POINTS
    other = (coins_collected(partner) if partner else 0) * COIN_POINTS
    preview = slider_preview(
        "contract-slider",
        "contract-output",
        f"""
        out.innerHTML = '<p class="live-note">With this round&rsquo;s coins, '
            + "your proposal would divide the points like this:</p>" + splitTable(v, {own}, {other});
        """,
    )
    prompt = Markup(
        f"""
        <h3>Propose a new contract</h3>
        <p>This round used <strong>{contract_label(contract)}</strong>.
        Move the slider to propose the contract for the <strong>next</strong> round.
        Your partner proposes one too, and the next round uses <strong>the average</strong> of both.</p>
        {preview}
        {slider_frame("contract-slider", *CONTRACT_ENDS, CONTRACT_STEPS, below="contract-output")}
        """
    )
    return ModularPage(
        "propose_contract",
        Prompt(prompt),
        SliderControl(
            start_value=contract,
            min_value=0,
            max_value=1,
            n_steps=CONTRACT_STEPS,
            slider_id="contract-slider",
            minimal_interactions=1,
            bot_response=0.5,
        ),
        time_estimate=CONTRACT_SECONDS,
    )


def summary_page(participant: Participant) -> InfoPage:
    scores = participant.var.get("scores", {})
    rows = "".join(
        f"<tr><td>Round {r}</td><td class='num'>{s:+d}</td></tr>"
        for r, s in sorted(scores.items())
    )
    return InfoPage(
        Markup(
            f"""
            <h3>Game over</h3>
            <p>Thank you for playing. Your points:</p>
            <table class="points-table">
                <tr><td>Start</td><td class="num">{START_BALANCE}</td></tr>{rows}
                <tr class="total final"><td>Final points</td><td class="num">{balance(participant)}</td></tr>
            </table>
            """
        ),
        time_estimate=10,
    )


class ForagingTrucksTrial(StaticTrial):
    time_estimate = TRIAL_TIME_ESTIMATE
    accumulate_answers = True

    def show_trial(self, experiment, participant):
        round_index = self.position
        # Barrier IDs are scoped by node: both players share it, and each round has its own.
        return join(
            PageMaker(
                lambda participant: buy_moves_page(participant, round_index),
                time_estimate=MOVES_SECONDS,
            ),
            crew_barrier(
                f"moves_{self.node_id}",
                "Waiting for your partner to finish buying moves...",
            ),
            PageMaker(
                lambda participant: ForagingPage(
                    participant,
                    round_id=self.node_id,
                    moves=moves_bought(participant),
                    title=f"<h3>Round {round_index + 1} of {N_ROUNDS}: collect coins</h3>",
                    terrain=ROUND_TERRAINS[round_index % len(ROUND_TERRAINS)],
                ),
                time_estimate=FORAGING_DURATION,
            ),
            crew_barrier(
                f"foraging_{self.node_id}",
                "Waiting for your partner to finish the round...",
            ),
            CodeBlock(lambda participant: store_score(participant, round_index)),
            PageMaker(score_page, time_estimate=SCORE_SECONDS),
            PageMaker(propose_contract_page, time_estimate=CONTRACT_SECONDS),
            crew_barrier(
                f"proposal_{self.node_id}",
                "Waiting for your partner's proposal...",
                on_release=average_proposals,
            ),
        )


trial_maker = StaticTrialMaker(
    id_="foraging_trucks",
    trial_class=ForagingTrucksTrial,
    nodes=START_NODES,
    expected_trials_per_participant=N_ROUNDS,
    max_trials_per_participant=N_ROUNDS,
    recruit_mode="n_participants",
    target_n_participants=20,
    sync_group_type=GROUP_TYPE,
)


class Exp(psynet.experiment.Experiment):
    label = "Foraging trucks"
    css_links = ["static/foraging.css"]

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
                """
                <h3>Welcome</h3>
                <p>In this game you team up with another player to collect coins.</p>
                """
                + (
                    """
                <p>First, three short tutorials show you how to play. Then we pair you
                with a partner.</p>
                """
                    if INCLUDE_TUTORIAL
                    else """
                <p>Next we pair you with a partner, and then the game starts.</p>
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
                contract_tutorial(SPLIT_JS, split_parts, FIXED_COST, COIN_POINTS),
            ]
            if INCLUDE_TUTORIAL
            else []
        ),
        SimpleGrouper(
            GROUP_TYPE,
            initial_group_size=MIN_PLAYERS,
            max_group_size=MIN_PLAYERS,
            min_group_size=MIN_PLAYERS,
            join_existing_groups=True,
            max_wait_time=120,
            waiting_logic=wait_page(
                "Waiting for a partner to join you. Please keep this page open; "
                "the game starts as soon as another player is ready."
            ),
        ),
        trial_maker,
        PageMaker(summary_page, time_estimate=10),
    )

    test_n_bots = 2

    def test_serial_run_bots(self, bots: List[BotDriver]):
        # The bots have to advance in lockstep, otherwise the first bot would sit at
        # the grouper and at the barriers until it timed out.
        max_pages = 200
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
        assert len(bot.var.get("scores", {})) == N_ROUNDS
