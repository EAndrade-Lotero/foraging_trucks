import json
import math
import os
import time
from typing import List

import psynet.experiment
from markupsafe import Markup
from psynet.bot import Bot, BotDriver
from psynet.modular_page import ModularPage, Prompt, SliderControl
from psynet.page import InfoPage, WaitPage
from psynet.participant import Participant
from psynet.sync import GroupBarrier, SimpleGrouper
from psynet.timeline import CodeBlock, PageMaker, Timeline, conditional, join
from psynet.trial.static import StaticNode, StaticTrial, StaticTrialMaker

from .foraging import (
    FORAGING_DURATION,
    GRID_SIZE,
    MAPS_DIR,
    MIN_PLAYERS,
    PLAYER_COLORS,
    ROUND_TERRAINS,
    EnableForaging,
    ForagingPage,
    last_valid_answer,
    patch_dallinger_sockets,
)
from .game_parameters import (
    CONTRACT_BLOCK,
    FOOD_MOVES,
    INCLUDE_TUTORIAL,
    INITIAL_FOOD,
    MAX_MOVES,
    N_ROUNDS,
    FOOD_CONVERSION,
    SOLO_FOOD_FACTOR,
    SOLO_MAX_ROUNDS,
    STALE_FOOD,
    START_MOVES,
)
from .tutorial import (
    CONTRACT_ENDS,
    buying_moves_tutorial,
    contract_tutorial,
    moving_tutorial,
    slider_frame,
    split_scene,
)


GROUP_TYPE = "crew"

# Economy (game_parameters.py): everything is counted in moves. Players invest moves from their
# bank, collect points (each worth FOOD_CONVERSION moves), the contract shares the points, and food
# is paid. A player whose bank reaches zero is out; their partner plays on alone.
START_CONTRACT = 0.0  # 0 = commission (keep your points), 1 = wages (equal split)

TUTORIAL_SECONDS = 30
MOVES_SECONDS = 20
SCORE_SECONDS = 20
CONTRACT_SECONDS = 20
# A player who does not reach a barrier within PARTNER_TIMEOUT_SECONDS of their partner (closed
# the tab, lost the connection) is taken out of the pair, and the partner plays on alone
# (Thomas, 12-oct). It is longer than the longest normal stretch between two barriers (a
# 60-second round plus reading). BARRIER_MAX_WAIT_SECONDS only fails a player stuck waiting.
PARTNER_TIMEOUT_SECONDS = 150
BARRIER_MAX_WAIT_SECONDS = 300
BARRIER_EXPECTED_WAIT = 10
TRIAL_TIME_ESTIMATE = (
    MOVES_SECONDS
    + BARRIER_EXPECTED_WAIT
    + FORAGING_DURATION
    + SCORE_SECONDS
    + CONTRACT_SECONDS / CONTRACT_BLOCK
)


# The node only identifies the round slot; the contract lives in the sync group,
# because it changes with the players' proposals.
START_NODES = [StaticNode(definition={"slot": i}) for i in range(N_ROUNDS)]


def _as_float(value, default=0.0):
    """A finite float, or `default` (answers come from the browser: "NaN" or "oops" too)."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def crew(participant: Participant):
    return participant.active_sync_groups[GROUP_TYPE]


def current_contract(participant: Participant) -> float:
    return _as_float(crew(participant).var.get("contract", START_CONTRACT))


def transfer(contract: float, own: int, partner: int) -> int:
    """Moves the first player gives to the other under the commission-wages rule (slides 11-13).

    `own` and `partner` are the points each one collected. Commission keeps (1 - contract) of
    your own; wages pool the rest of both and split the pot equally. Together that is one
    transfer of contract * (own - partner) / 2 points, rounded to the nearest half point (half
    away from zero) and paid in moves (FOOD_CONVERSION per point, an even number). So full wages are
    always exactly equal, and static/split_scene.js, which draws half points, shows exactly
    what is paid.
    """
    halves = contract * (own - partner)
    whole = int(abs(halves) + 0.5 + 1e-9)
    return (whole if halves >= 0 else -whole) * FOOD_CONVERSION // 2


def split(contract: float, own: int, partner: int) -> int:
    """Moves the first player gets from the points both collected."""
    return own * FOOD_CONVERSION - transfer(contract, own, partner)


def signed(n: int) -> str:
    return f"+ {n}" if n > 0 else (f"− {-n}" if n < 0 else "0")


def contribution_percent(contract: float) -> str:
    """The group-contribution slider, as a percent. Averages can fall between the 10% marks."""
    pct = 100 * _as_float(contract)
    return str(int(round(pct))) if abs(pct - round(pct)) < 1e-6 else f"{pct:.1f}"


def contract_label(contract: float) -> str:
    return f"{contribution_percent(contract)}% group contribution"


def points(n: int) -> str:
    return f"{n} point" if n == 1 else f"{n} points"


def moves(n: int) -> str:
    return f"{n} move" if n == 1 else f"{n} moves"


def points_collected(participant: Participant) -> int:
    """Points reported by the board page, never more than the round's map holds (the answer
    comes from the browser; counting on the server is still to do)."""
    answer = last_valid_answer(participant, "foraging_page")
    if not isinstance(answer, dict):
        return 0
    most = map_points(answer.get("terrain"))
    return int(min(max(_as_float(answer.get("coins_collected", 0)), 0), most))


def map_points(terrain) -> int:
    try:
        return len(json.loads((MAPS_DIR / f"{terrain}.json").read_text()))
    except (OSError, ValueError, TypeError):
        return GRID_SIZE * GRID_SIZE


def accumulated_food(participant: Participant) -> int:
    """Food on hand before this round's stale food is taken."""
    total = INITIAL_FOOD
    for r in results(participant):
        total += int(r.get("own", 0)) - int(r.get("food_spent", 0)) - STALE_FOOD
    return total


def food_available(participant: Participant) -> int:
    """Food left to invest after this round's stale food."""
    return max(0, accumulated_food(participant) - STALE_FOOD)


def investable_food(participant: Participant) -> int:
    """Food the slider can turn into moves this round."""
    cap = MAX_MOVES // FOOD_CONVERSION if FOOD_CONVERSION else 0
    return min(food_available(participant), cap)


def food_spent_answer(participant: Participant) -> int:
    """The invest-slider answer, in food, kept within what the slider allowed."""
    top = investable_food(participant)
    if top <= 0:
        return 0
    return int(min(max(_as_float(last_valid_answer(participant, "buy_moves")), 0), top))


def moves_invested(participant: Participant) -> int:
    """Moves this round: each unit of food invested becomes FOOD_CONVERSION moves."""
    return food_spent_answer(participant) * FOOD_CONVERSION


def bank(participant: Participant) -> int:
    """Moves carried over: the starting bank plus every finished round."""
    return START_MOVES + sum(participant.var.get("scores", {}).values())


def results(participant: Participant) -> list:
    return participant.var.get("results", [])


def is_out(participant: Participant) -> bool:
    return participant.var.get("out_round", None) is not None


def is_solo(participant: Participant) -> bool:
    return participant.var.get("partner_out_round", None) is not None


def partner_gone(participant: Participant) -> str:
    return ("left the game" if participant.var.get("partner_left", False)
            else "ran out of moves")


def left_game(participant: Participant) -> bool:
    """Taken out of the pair for being away too long (see PARTNER_TIMEOUT_SECONDS)."""
    return GROUP_TYPE not in participant.active_sync_groups and not is_out(participant)


def in_game(participant: Participant) -> bool:
    return not is_out(participant) and not left_game(participant)


def game_ended_page() -> InfoPage:
    """For a player taken out of the pair who reloads a page they had open."""
    return InfoPage(
        Markup("<h3>The game has ended for you</h3><p>You were away from the game for too "
               "long, so your partner continued alone. Click Next to finish.</p>"),
        time_estimate=5,
    )


def if_playing(make_page):
    """Build the page only while the player is still in the game."""
    return lambda participant: make_page(participant) if in_game(participant) else game_ended_page()


def notice_if_alone(participant: Participant):
    """If the partner was taken out between rounds, play this round alone (and say so)."""
    if in_game(participant) and not is_solo(participant) and len(crew(participant).participants) == 1:
        participant.var.set("partner_out_round", len(results(participant)) + 1)
        participant.var.set("partner_left", True)


def store_investment(participant: Participant):
    """The investment the game uses, checked against the food on hand, right after the page."""
    spent = food_spent_answer(participant)
    participant.var.set("food_spent", spent)
    participant.var.set("invested", spent * FOOD_CONVERSION)


def solo_rounds(participant: Participant) -> int:
    return sum(1 for r in results(participant) if r["solo"])


def score_round(group, participants, participant, barrier):
    """Runs once when both players have finished foraging: shares the points and pays.

    Both results are computed here, together, so that a player who runs out of moves can leave
    the group without changing their partner's result for the same round.
    """
    if group.var.get("scored_barrier", None) == barrier.id:
        return
    group.var.set("scored_barrier", barrier.id)
    players = sorted(participants, key=lambda p: p.id)
    contract = _as_float(group.var.get("contract", START_CONTRACT))
    solo = len(players) == 1
    if solo and not is_solo(players[0]):
        # The partner was taken out for being away too long: from now on, play alone.
        players[0].var.set("partner_out_round", len(results(players[0])) + 1)
        players[0].var.set("partner_left", True)
    collected = {p.id: points_collected(p) for p in players}
    for i, p in enumerate(players):
        if not solo:
            p.var.set("color_index", i)  # as on the board, where colours follow participant IDs
        others = [q for q in players if q.id != p.id]
        own = collected[p.id]
        other = collected[others[0].id] if others else 0
        gained = own * FOOD_CONVERSION if solo else split(contract, own, other)
        food = FOOD_MOVES * (SOLO_FOOD_FACTOR if solo else 1)
        invested = p.var.get("invested", None)
        if invested is None:
            invested = moves_invested(p)
        score = gained - invested - food
        round_number = len(results(p)) + 1
        result = dict(
            round=round_number, solo=solo, contract=None if solo else contract,
            own=own, other=other, gained=gained, invested=invested, food=food, score=score,
            food_spent=int(p.var.get("food_spent", 0) or 0),
        )
        p.var.set("results", results(p) + [result])
        scores = p.var.get("scores", {})
        scores[str(round_number)] = score
        p.var.set("scores", scores)
    for p in players:
        if bank(p) <= 0:
            p.var.set("out_round", len(results(p)))
            group.remove_participant(p)  # the partner plays on alone (min_group_size is 1)
            for q in players:
                if q.id != p.id and bank(q) > 0:
                    q.var.set("partner_out_round", len(results(q)))


def average_proposals(group, participants, participant, barrier):
    """Runs when both players have proposed: the next contract is their average."""
    proposals = [
        _as_float(last_valid_answer(p, "propose_contract"), None) for p in participants
    ]
    # Within the slider's range (the answer comes from the browser).
    proposals = [min(max(p, 0.0), 1.0) for p in proposals if p is not None]
    if len(participants) == 1 and not is_solo(participants[0]):
        # The partner was taken out while proposing: from now on, play alone.
        participants[0].var.set("partner_out_round", len(results(participants[0])) + 1)
        participants[0].var.set("partner_left", True)
    if proposals:
        # The exact average (it can fall between the slider's 10% marks, e.g. 5%).
        group.var.set("contract", sum(proposals) / len(proposals))


CONTRACT_STEPS = 11  # 0%, 10%, ..., 100% group contribution


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
        participant_timeout=PARTNER_TIMEOUT_SECONDS,
        participant_timeout_action="kick",
        on_release=on_release,
    )


def tutorial_page() -> InfoPage:
    return InfoPage(
        Markup(
            f"""
            <h3>How the game works</h3>
            <p>You start with <strong>{INITIAL_FOOD} food</strong> and play up to
            <strong>{N_ROUNDS} rounds</strong> with a partner, each on a new board. Each round:</p>
            <ol>
                <li><strong>Invest food</strong> from your bank. Each unit becomes
                    {FOOD_CONVERSION} moves, the steps your pac-man can take.
                    <strong>{STALE_FOOD} food</strong> goes stale every round.</li>
                <li><strong>Collect points</strong> in a dark cave, with a torch. Points are food.</li>
                <li><strong>Share the points</strong> by the group contribution. The game turns
                    them into moves for you and pays for food.</li>
            </ol>
            <p>Every {CONTRACT_BLOCK} rounds you and your partner propose a new contract.
            If your bank runs out, you are out of the game and your partner goes on alone.</p>
            """
        ),
        time_estimate=TUTORIAL_SECONDS,
    )


def colors(participant: Participant) -> tuple:
    """The pac-man colours of this player and their partner, as on the board."""
    me = participant.var.get("color_index", 0)
    return PLAYER_COLORS[me], PLAYER_COLORS[1 - me]


def food_panel(accumulated: int) -> str:
    """The food on hand, and the stale-food parameter, before this round's subtraction."""
    return f"""
        <div class="food-panel">
            <div>
                <div class="food-panel-label">Accumulated food</div>
                <div class="food-panel-note">Stale food: {STALE_FOOD} per round</div>
            </div>
            <div class="food-panel-value">{accumulated}</div>
        </div>
    """


def food_table(participant: Participant) -> str:
    """Initial food, then each finished round, then this round's stale food taken off."""
    rows = [f"<tr><td>Initial food</td><td class='num'>{INITIAL_FOOD}</td></tr>"]
    running = INITIAL_FOOD
    for r in results(participant):
        n = r["round"]
        rows.append(f"<tr><td>Collected, round {n}</td><td class='num'>{signed(int(r.get('own', 0)))}</td></tr>")
        running += int(r.get("own", 0))
        spent = int(r.get("food_spent", 0))
        rows.append(f"<tr><td>Invested, round {n}</td><td class='num'>{signed(-spent)}</td></tr>")
        running -= spent
        rows.append(f"<tr><td>Stale food, round {n}</td><td class='num'>{signed(-STALE_FOOD)}</td></tr>")
        running -= STALE_FOOD
    available = max(0, running - STALE_FOOD)
    can_invest = investable_food(participant)
    if results(participant):
        rows.append(f"<tr class='total'><td>Accumulated food</td><td class='num'>{running}</td></tr>")
    rows.append(f"<tr><td>Stale food, this round</td><td class='num'>{signed(-STALE_FOOD)}</td></tr>")
    rows.append(f"<tr class='total'><td>Food you can invest</td><td class='num'>{can_invest}</td></tr>")
    if can_invest < available:
        cap = MAX_MOVES // FOOD_CONVERSION
        rows.append(
            f"<tr><td colspan='2'><span class='note'>At most {cap} food can become moves "
            f"this round ({MAX_MOVES} moves).</span></td></tr>"
        )
    return "<table class='points-table'>" + "".join(rows) + "</table>"


def buy_moves_page(participant: Participant, round_index: int) -> ModularPage:
    """Same layout as tutorial 1: the food bank turns into moves as the slider moves."""
    accumulated = accumulated_food(participant)
    top = investable_food(participant)
    solo = ""
    if is_solo(participant):
        solo = (
            f"<p>Your partner {partner_gone(participant)}, so you play <strong>alone</strong>. "
            f"You can play at most {SOLO_MAX_ROUNDS - solo_rounds(participant)} more rounds.</p>"
        )
    if top <= 0:
        # SliderControl rejects max == min, so the control stays submittable but hidden.
        converter = "<p>You have no food left to turn into moves this round.</p>"
        frame = "<style>#moves-slider { display: none; }</style>"
        slider = SliderControl(
            start_value=0, min_value=0, max_value=1, n_steps=2,
            slider_id="moves-slider", minimal_interactions=0, bot_response=0,
        )
    else:
        converter = f"""
        <div id="round-convert" class="scene-box"></div>
        <script src="/static/convert_scene.js"></script>
        <div id="moves-output" class="live-value"></div>
        {slider_frame("moves-slider", "", "", top + 1, below="moves-output", values=list(range(top + 1)))}
        <script>
        psynet.trial.onEvent("trialConstruct", function () {{
            var slider = document.getElementById("moves-slider");
            var convert = ConvertScene(document.getElementById("round-convert"),
                                       {{bank: {top}, perPoint: {FOOD_CONVERSION}}});
            var out = document.getElementById("moves-output");
            function show(animate) {{
                var v = parseInt(slider.value, 10);
                convert.set(v, animate);
                out.innerHTML = "<em>Instruction: invest " + v + " food</em>";
            }}
            slider.addEventListener("input", function () {{ show(true); }});
            show(false);
        }});
        </script>
        """
        frame = ""
        slider = SliderControl(
            start_value=0,
            min_value=0,
            max_value=top,
            n_steps=top + 1,
            slider_id="moves-slider",
            minimal_interactions=0,  # Next works from the start: investing nothing is allowed
            bot_response=min(2, top),
        )
    prompt = Markup(
        f"""
        <h3>Round {round_index + 1} of {N_ROUNDS}: food and moves</h3>
        <p>This is your <strong>food bank</strong>. Here you can turn food into moves for foraging.
        <strong>Each unit of food is worth {FOOD_CONVERSION} moves.</strong></p>
        {solo}
        {food_panel(accumulated)}
        {food_table(participant)}
        {converter}
        {frame}
        """
    )
    return ModularPage(
        "buy_moves",
        Prompt(prompt),
        slider,
        time_estimate=MOVES_SECONDS,
    )


def ledger(r: dict, after: int) -> str:
    """The round in moves, already added up: the participant never has to compute."""
    food = "Food (alone: × " + str(SOLO_FOOD_FACTOR) + ")" if r["solo"] else "Food"
    return f"""
        <table class="points-table">
            <tr><td>Your share of the points</td><td class="num">{signed(r["gained"])} moves</td></tr>
            <tr><td>Moves you invested</td><td class="num">{signed(-r["invested"])}</td></tr>
            <tr><td>{food}</td><td class="num">{signed(-r["food"])}</td></tr>
            <tr class="total"><td>This round</td><td class="num">{signed(r["score"])}</td></tr>
            <tr><td>Your bank</td><td class="num">{after - r["score"]} → <strong>{max(after, 0)}</strong></td></tr>
        </table>
    """


def score_page(participant: Participant) -> InfoPage:
    r = results(participant)[-1]
    after = bank(participant)
    you, partner = colors(participant)
    head = f"You gained {moves(r['score'])}" if r["score"] >= 0 else f"You lost {moves(-r['score'])}"
    if r["solo"]:
        body = f"<p>You played alone and collected <strong>{points(r['own'])}</strong>.</p>"
    else:
        scene = split_scene("score-scene", "", r["own"], r["other"], r["contract"],
                            you_color=you, partner_color=partner, fixed=True, play_from=0)
        body = f"""
            <p>You collected <strong>{points(r["own"])}</strong> and your partner
            <strong>{points(r["other"])}</strong>.</p>
            <div class="contribution-panel">
                <div class="contribution-panel-label">Group contribution</div>
                <div class="contribution-panel-value">{contribution_percent(r["contract"])}%</div>
            </div>
            <p>The group contribution shares the points:</p>
            {scene}
        """
    if is_out(participant):
        tail = """<p class="out-note"><strong>Your bank is empty: you are out of the game.</strong>
                  """ + ("" if r["solo"] else "Your partner continues alone.") + "</p>"
    elif participant.var.get("partner_out_round", None) == r["round"]:
        tail = f"""<p class="out-note"><strong>Your partner {partner_gone(participant)}.</strong> From now on
                   you play alone, for at most {SOLO_MAX_ROUNDS} more rounds.</p>"""
    else:
        tail = ""
    return InfoPage(
        Markup(f"<h3>{head} this round</h3>{body}{ledger(r, after)}{tail}"),
        time_estimate=SCORE_SECONDS,
    )


def propose_contract_page(participant: Participant) -> ModularPage:
    contract = current_contract(participant)
    r = results(participant)[-1]
    you, partner = colors(participant)
    scene = split_scene("propose-scene", "contract-slider", r["own"], r["other"], contract,
                        you_color=you, partner_color=partner)
    prompt = Markup(
        f"""
        <h3>Propose the group contribution</h3>
        <p>The last {CONTRACT_BLOCK} rounds used <strong>{contract_label(contract)}</strong>.
        Move the slider to propose the group contribution for the <strong>next {CONTRACT_BLOCK} rounds</strong>.
        Your partner proposes one too, and the game uses <strong>the average</strong> of both.</p>
        <p class="live-note">With this round's points (you {r["own"]}, your partner {r["other"]}),
        your proposal would share them like this:</p>
        {scene}
        {slider_frame("contract-slider", *CONTRACT_ENDS, CONTRACT_STEPS)}
        """
    )
    return ModularPage(
        "propose_contract",
        Prompt(prompt),
        SliderControl(
            start_value=round(contract * 10) / 10,  # the nearest mark of the slider
            min_value=0,
            max_value=1,
            n_steps=CONTRACT_STEPS,
            slider_id="contract-slider",
            minimal_interactions=0,  # Next works from the start: the current contract is a valid proposal
            bot_response=0.5,
        ),
        time_estimate=CONTRACT_SECONDS,
    )


def summary_page(participant: Participant) -> InfoPage:
    rows = "".join(
        f"<tr><td>Round {r['round']}{' (alone)' if r['solo'] else ''}</td>"
        f"<td class='num'>{signed(r['score'])}</td></tr>"
        for r in results(participant)
    )
    if is_out(participant):
        how = f"You ran out of moves in round {participant.var.get('out_round')}."
    elif left_game(participant):
        how = ("You were away from the game for too long, so it ended for you and your "
               "partner continued alone.")
    elif is_solo(participant):
        how = (f"Your partner {partner_gone(participant)} in round "
               f"{participant.var.get('partner_out_round')}; "
               "you played on alone.")
    else:
        how = f"You and your partner played all {N_ROUNDS} rounds."
    return InfoPage(
        Markup(
            f"""
            <h3>Game over</h3>
            <p>{how} Thank you for playing. Your bank of moves:</p>
            <table class="points-table">
                <tr><td>Start</td><td class="num">{START_MOVES}</td></tr>{rows}
                <tr class="total final"><td>Final bank</td><td class="num">{max(bank(participant), 0)}</td></tr>
            </table>
            """
        ),
        time_estimate=10,
    )


def proposes_after(round_index: int) -> bool:
    """A new contract is proposed after each block of CONTRACT_BLOCK rounds (not after the last)."""
    return (round_index + 1) % CONTRACT_BLOCK == 0 and round_index + 1 < N_ROUNDS


class ForagingTrucksTrial(StaticTrial):
    time_estimate = TRIAL_TIME_ESTIMATE
    accumulate_answers = True

    def show_trial(self, experiment, participant):
        round_index = self.position

        def playing(*elts, label):
            # A player taken out for being away too long skips the rest of the round; the
            # trial maker then ends their game (ForagingTrialMaker.game_over).
            return conditional(f"{label}_{round_index}", in_game, join(*elts))

        # Barrier IDs are scoped by node: both players share it, and each round has its own.
        return join(
            playing(
                CodeBlock(notice_if_alone),
                PageMaker(
                    if_playing(lambda participant: buy_moves_page(participant, round_index)),
                    time_estimate=MOVES_SECONDS,
                ),
                CodeBlock(store_investment),
                label="invest",
            ),
            crew_barrier(
                f"moves_{self.node_id}",
                "Waiting for your partner to finish investing food...",
            ),
            playing(
                PageMaker(
                    if_playing(lambda participant: ForagingPage(
                        participant,
                        round_id=self.node_id,
                        moves=participant.var.get("invested", 0),
                        title=f"<h3>Round {round_index + 1} of {N_ROUNDS}: collect points</h3>",
                        terrain=ROUND_TERRAINS[round_index % len(ROUND_TERRAINS)],
                    )),
                    time_estimate=FORAGING_DURATION,
                ),
                label="forage",
            ),
            crew_barrier(
                f"foraging_{self.node_id}",
                "Waiting for your partner to finish the round...",
                on_release=score_round,
            ),
            conditional(
                f"score_{round_index}",
                lambda participant: not left_game(participant),
                PageMaker(score_page, time_estimate=SCORE_SECONDS),
            ),
            # Players who are out, alone or gone do not propose (and must not wait at a barrier).
            conditional(
                f"propose_{round_index}",
                lambda participant: (
                    proposes_after(round_index)
                    and in_game(participant)
                    and not is_solo(participant)
                ),
                join(
                    PageMaker(if_playing(propose_contract_page), time_estimate=CONTRACT_SECONDS),
                    crew_barrier(
                        f"proposal_{self.node_id}",
                        "Waiting for your partner's proposal...",
                        on_release=average_proposals,
                    ),
                ),
            ),
        )


class ForagingTrialMaker(StaticTrialMaker):
    """Stops a player's rounds when they are out, or after SOLO_MAX_ROUNDS rounds alone."""

    def compile_elts(self):
        # StaticTrialMaker does not pass sync_group_max_wait_time on, and its default (45 s)
        # would fail a player whose partner is still reading the round result.
        self.sync_group_max_wait_time = BARRIER_MAX_WAIT_SECONDS
        return super().compile_elts()

    @staticmethod
    def game_over(participant: Participant) -> bool:
        return (
            is_out(participant)
            or left_game(participant)
            or solo_rounds(participant) >= SOLO_MAX_ROUNDS
        )

    def prepare_trial(self, experiment, participant):
        if self.game_over(participant):
            return None, "exit"
        return super().prepare_trial(experiment, participant)

    def prepare_follower_trial(self, experiment, participant, leader):
        if self.game_over(participant):
            return None, "exit"
        return super().prepare_follower_trial(experiment, participant, leader)


trial_maker = ForagingTrialMaker(
    id_="foraging_trucks",
    trial_class=ForagingTrucksTrial,
    nodes=START_NODES,
    expected_trials_per_participant=N_ROUNDS,
    max_trials_per_participant=N_ROUNDS,
    recruit_mode="n_participants",
    target_n_participants=20,
    sync_group_type=GROUP_TYPE,
    # Between rounds PsyNet waits for the pair at its own barrier: same rule as ours.
    sync_group_timeout=PARTNER_TIMEOUT_SECONDS,
    sync_group_timeout_action="kick",
)


class Exp(psynet.experiment.Experiment):
    label = "Foraging trucks"
    css_links = ["static/foraging.css"]

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
                """
                <h3>Welcome</h3>
                <p>In this game you team up with another player to collect points.</p>
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
                contract_tutorial(),
            ]
            if INCLUDE_TUTORIAL
            else []
        ),
        SimpleGrouper(
            GROUP_TYPE,
            initial_group_size=MIN_PLAYERS,
            min_group_size=1,  # after a partner leaves or runs out, the other plays on alone
            # Pairs form only from players waiting together: PsyNet would otherwise let a new
            # player join any group with room, including one whose partner ran out of moves.
            join_existing_groups=False,
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
