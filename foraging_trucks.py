"""Foraging-trucks rounds: food economy, pair pages, and the trial maker.

The PsyNet experiment in experiment.py places this trial maker on the timeline.
"""

import json
import math

from markupsafe import Markup
from psynet.modular_page import ModularPage, Prompt, SliderControl
from psynet.page import InfoPage, WaitPage
from psynet.participant import Participant
from psynet.sync import GroupBarrier
from psynet.timeline import CodeBlock, PageMaker, conditional, join
from psynet.trial.static import StaticNode, StaticTrial, StaticTrialMaker

from .foraging import (
    FORAGING_DURATION,
    GRID_SIZE,
    MAPS_DIR,
    PLAYER_COLORS,
    ROUND_TERRAINS,
    ForagingPage,
    last_valid_answer,
)
from .game_parameters import (
    CONTRACT_BLOCK,
    FOOD_CONVERSION,
    FOOD_MOVES,
    INITIAL_FOOD,
    MAX_MOVES,
    MIN_GROUP_SIZE,
    N_ROUNDS,
    SOLO_FOOD_FACTOR,
    STALE_FOOD,
    START_CONTRACT,
    START_MOVES,
)
from .grouping import Quorum
from .pairing import (
    CREW_GROUP,
    assign_round_pairs,
    finish_round,
    proposes_this_round,
    record_pair_contract,
)
from .tutorial import (
    CONTRACT_ENDS,
    slider_frame,
    split_scene,
)


GROUP_TYPE = CREW_GROUP

# Economy (game_parameters.py): everything is counted in moves. Players invest moves from their
# bank, collect points (each worth FOOD_CONVERSION moves), the contract shares the points, and food
# is paid. A player whose bank reaches zero is out; their partner plays on alone.
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
# Longest wait for a partner before the game; after it the study ends (PsyNet fails the
# participant at the grouper) and they are paid for their time. Prolific asks to say both
# before the study starts.
PARTNER_WAIT_SECONDS = 120
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


def has_food_to_continue(participant: Participant) -> bool:
    """True when more than one round of stale food is left, so another round can start."""
    return accumulated_food(participant) > STALE_FOOD


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
            else "ran out of food")


def left_game(participant: Participant) -> bool:
    """Taken out of the group for being away too long (see PARTNER_TIMEOUT_SECONDS)."""
    return bool(participant.var.get("left_game", False))


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


def note_if_kicked(participant: Participant):
    """A partner-timeout removes the player from the pair. Take them out of the quorum too.

    Sitting a round out also leaves them without a pair. That is not a kick.
    """
    if is_out(participant) or participant.var.get("sitting_out", False):
        return
    if GROUP_TYPE in participant.active_sync_groups:
        return
    quorum = participant.active_sync_groups.get(Quorum.GROUP)
    if quorum is None:
        return
    participant.var.set("left_game", True)
    quorum.remove_participant(participant)


def notice_if_alone(participant: Participant):
    """If the partner was taken out between rounds, play this round alone (and say so)."""
    if (
        in_game(participant)
        and not is_solo(participant)
        and GROUP_TYPE in participant.active_sync_groups
        and len(crew(participant).participants) == 1
    ):
        participant.var.set("partner_out_round", len(results(participant)) + 1)
        participant.var.set("partner_left", True)


def store_investment(participant: Participant):
    """The investment the game uses, checked against the food on hand, right after the page."""
    spent = food_spent_answer(participant)
    participant.var.set("food_spent", spent)
    participant.var.set("invested", spent * FOOD_CONVERSION)


def _players_still_in(quorum) -> int:
    """Quorum members who can still be paired."""
    return sum(
        1
        for person in quorum.active_participants
        if person.var.get("out_round", None) is None
        and not person.var.get("left_game", False)
    )


def score_round(group, participants, participant, barrier):
    """Runs once when both players have finished foraging: shares the points and pays.

    Both results are computed here, together, so that a player who cannot cover the next
    round's stale food can leave the group without changing their partner's result.
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
    for p in players:
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
        # Food on hand now includes this round. Less than or equal to the stale food means
        # the next round cannot start.
        if not has_food_to_continue(p):
            p.var.set("out_round", len(results(p)))
            group.remove_participant(p)  # the partner plays on alone (min_group_size is 1)
            quorum = p.active_sync_groups.get(Quorum.GROUP)
            if quorum is not None:
                quorum.remove_participant(p)
            for q in players:
                if q.id != p.id and has_food_to_continue(q):
                    q.var.set("partner_out_round", len(results(q)))


def average_proposals(group, participants, participant, barrier):
    """Runs when both players have proposed: the next contract is their average.

    Each pair's agreement is also folded into the quorum contract, which the
    next round's pairs start from.
    """
    if group.var.get("proposal_barrier", None) == barrier.id:
        return
    group.var.set("proposal_barrier", barrier.id)
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
        agreed = sum(proposals) / len(proposals)
        group.var.set("contract", agreed)
        record_pair_contract(participants[0], agreed)


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
        timeout_between_barriers_time=PARTNER_TIMEOUT_SECONDS,
        timeout_between_barriers_action="kick",
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
    """Each participant sees themself in yellow and their partner in red."""
    return PLAYER_COLORS[0], PLAYER_COLORS[1]


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
    """The same lines every round: food at the start, this round's stale food, then what can be invested.

    On the first round the start is the initial food. Later rounds use the food carried over,
    without listing each earlier round again.
    """
    start = accumulated_food(participant)
    available = max(0, start - STALE_FOOD)
    can_invest = investable_food(participant)
    rows = [
        f"<tr><td>Initial food</td><td class='num'>{start}</td></tr>",
        f"<tr><td>Stale food, this round</td><td class='num'>{signed(-STALE_FOOD)}</td></tr>",
        f"<tr class='total'><td>Food you can invest</td><td class='num'>{can_invest}</td></tr>",
    ]
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
            f"<p>Your partner {partner_gone(participant)}, so you play <strong>alone</strong> "
            "this round. If the group still has enough players, you are paired again "
            "next round.</p>"
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


def ledger(initial_food: int, invested_food: int, net: int, food_bank: int) -> str:
    """This round's food, already added up: initial, invested, stale, then the food on hand."""
    return f"""
        <table class="points-table">
            <tr><td>Initial food</td><td class="num">{initial_food}</td></tr>
            <tr><td>Food invested</td><td class="num">{signed(-invested_food)}</td></tr>
            <tr><td>Food gone stale</td><td class="num">{signed(-STALE_FOOD)}</td></tr>
            <tr class="total"><td>This round</td><td class="num">{signed(net)}</td></tr>
            <tr><td>Your bank</td><td class="num">{food_bank}</td></tr>
        </table>
    """


def score_page(participant: Participant) -> InfoPage:
    r = results(participant)[-1]
    you, partner_color = colors(participant)
    spent = int(r.get("food_spent", 0) or 0)
    own = int(r.get("own", 0))
    # results already include this round, so take it back out to get the food at the start.
    initial_food = accumulated_food(participant) - own + spent + STALE_FOOD
    net = own - spent - STALE_FOOD
    table = ledger(initial_food, spent, net, initial_food + net)
    if r["solo"]:
        body = f"""
            <p class="score-heading">Food collected this round:</p>
            <p>You played alone and collected <strong>{points(own)}</strong>.</p>
        """
    else:
        collected = split_scene(
            "collected-scene", "", own, int(r["other"]), 0,
            you_color=you, partner_color=partner_color, fixed=True, caption=False, legend=False,
        )
        kept = split_scene(
            "kept-scene", "", own, int(r["other"]), r["contract"],
            you_color=you, partner_color=partner_color, fixed=True, caption=False, legend=False,
        )
        body = f"""
            <p class="score-heading">Food collected this round:</p>
            {collected}
            <p class="score-heading">Current value of group contribution:</p>
            <div class="contribution-panel">
                <div class="contribution-panel-label">Group contribution</div>
                <div class="contribution-panel-value">{contribution_percent(r["contract"])}%</div>
            </div>
            <p class="score-heading">Food kept after contribution:</p>
            {kept}
        """
    if is_out(participant):
        tail = """<p class="out-note"><strong>You do not have enough food to continue: you are out of the game.</strong>
                  """ + ("" if r["solo"] else " The others keep playing.") + "</p>"
    elif participant.var.get("partner_out_round", None) == r["round"]:
        tail = f"""<p class="out-note"><strong>Your partner {partner_gone(participant)}.</strong>
                   You play this round alone. If the group still has enough players, you are
                   paired again next round.</p>"""
    else:
        tail = ""
    return InfoPage(
        Markup(f"{body}{table}{tail}"),
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
    """The game, in food: what you started with, each round, and the food left."""
    def round_food(r: dict) -> int:
        return int(r.get("own", 0)) - int(r.get("food_spent", 0) or 0) - STALE_FOOD

    rows = "".join(
        f"<tr><td>Round {r['round']}{' (alone)' if r['solo'] else ''}</td>"
        f"<td class='num'>{signed(round_food(r))}</td></tr>"
        for r in results(participant)
    )
    final = INITIAL_FOOD + sum(round_food(r) for r in results(participant))
    quorum = Quorum.for_participant(participant)
    ended_early = participant.var.get("ended_early") == "group_too_small" or (
        quorum is not None and quorum.var.get("ended_early") == "group_too_small"
    )
    if is_out(participant):
        how = f"You ran out of food in round {participant.var.get('out_round')}."
    elif ended_early:
        how = "The group became too small to keep playing, so the game ended early."
    elif left_game(participant):
        how = ("You were away from the game for too long, so it ended for you and your "
               "partner continued alone.")
    elif is_solo(participant):
        why = "left the game" if participant.var.get("partner_left", False) else "ran out of food"
        how = (f"Your partner {why} in round {participant.var.get('partner_out_round')}; "
               "you played on alone.")
    else:
        how = f"You and your partner played all {N_ROUNDS} rounds."
    return InfoPage(
        Markup(
            f"""
            <h3>Game over</h3>
            <p>{how} Thank you for playing. Your food:</p>
            <table class="points-table">
                <tr><td>Initial food</td><td class="num">{INITIAL_FOOD}</td></tr>{rows}
                <tr class="total final"><td>Your bank</td><td class="num">{final}</td></tr>
            </table>
            """
        ),
        time_estimate=10,
    )


def proposes_after(round_index: int) -> bool:
    """A new contract is proposed after each block of CONTRACT_BLOCK rounds (not after the last)."""
    return proposes_this_round(round_index)


def sit_out_page(participant: Participant) -> InfoPage:
    """Shown to a player who has no partner for this round."""
    quorum = Quorum.for_participant(participant)
    if quorum is not None and quorum.var.get("ended_early"):
        text = "The group no longer has enough players, so the game ends here."
    else:
        text = ("You are sitting this round out. You will be paired again when "
                "the next round starts.")
    return InfoPage(Markup(f"<h3>This round</h3><p>{text}</p>"), time_estimate=5)


class ForagingTrucksTrial(StaticTrial):
    time_estimate = TRIAL_TIME_ESTIMATE
    accumulate_answers = True

    def show_trial(self, experiment, participant):
        round_index = self.position

        def playing(*elts, label):
            # A player taken out for being away too long skips the rest of the round; the
            # trial maker then ends their game (ForagingTrialMaker.game_over).
            return conditional(f"{label}_{round_index}", in_game, join(*elts))

        # Barrier IDs are scoped by node: a pair shares them, and each round has its own.
        # The round starts by pairing the quorum. A player with no partner sits it out
        # and meets the others again at the quorum's barrier between rounds.
        return join(
            CodeBlock(lambda participant: assign_round_pairs(participant, round_index)),
            conditional(
                f"sit_{round_index}",
                lambda participant: bool(participant.var.get("sitting_out", False)),
                PageMaker(sit_out_page, time_estimate=5),
                join(
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
                    CodeBlock(note_if_kicked),
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
                    CodeBlock(note_if_kicked),
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
                            and not participant.var.get("sitting_out", False)
                        ),
                        join(
                            PageMaker(if_playing(propose_contract_page), time_estimate=CONTRACT_SECONDS),
                            crew_barrier(
                                f"proposal_{self.node_id}",
                                "Waiting for your partner's proposal...",
                                on_release=average_proposals,
                            ),
                            CodeBlock(note_if_kicked),
                        ),
                    ),
                ),
            ),
            CodeBlock(lambda participant: finish_round(participant, round_index)),
        )


class ForagingTrialMaker(StaticTrialMaker):
    """Stops a player's rounds when they are out, or when the group falls below the minimum."""

    @staticmethod
    def game_over(participant: Participant) -> bool:
        if participant.var.get("ended_early") == "group_too_small":
            return True
        quorum = participant.active_sync_groups.get(Quorum.GROUP)
        if (
            quorum is not None
            and quorum.var.get("game_opened")
            and _players_still_in(quorum) < MIN_GROUP_SIZE
        ):
            quorum.var.set("ended_early", "group_too_small")
            for person in quorum.active_participants:
                person.var.set("ended_early", "group_too_small")
            return True
        return is_out(participant) or left_game(participant)

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
    # The whole quorum advances a round together. Within a round, pair barriers
    # use the crew group assigned for that round.
    sync_group_type=Quorum.GROUP,
    # The default wait (45 s) would fail a player whose partner is still reading the result.
    sync_group_max_wait_time=BARRIER_MAX_WAIT_SECONDS,
    # Between rounds PsyNet waits for the quorum at its own barrier: same rule as ours.
    sync_group_timeout_between_barriers_time=PARTNER_TIMEOUT_SECONDS,
    sync_group_timeout_between_barriers_action="kick",
)
