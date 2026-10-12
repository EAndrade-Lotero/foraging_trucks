import json
from typing import List

import psynet.experiment
from markupsafe import Markup
from psynet.bot import Bot, BotDriver
from psynet.modular_page import ModularPage, Prompt, SliderControl
from psynet.page import InfoPage, WaitPage
from psynet.participant import Participant
from psynet.sync import GroupBarrier, SimpleGrouper
from psynet.timeline import PageMaker, Timeline, conditional, join
from psynet.trial.static import StaticNode, StaticTrial, StaticTrialMaker

from .foraging import (
    FORAGING_DURATION,
    GRID_SIZE,
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
    MAX_MOVES,
    MOVE_STEP,
    N_ROUNDS,
    POINT_MOVES,
    SOLO_FOOD_FACTOR,
    SOLO_MAX_ROUNDS,
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
# bank, collect points (each worth POINT_MOVES moves), the contract shares the points, and food
# is paid. A player whose bank reaches zero is out; their partner plays on alone.
START_CONTRACT = 0.0  # 0 = commission (keep your points), 1 = wages (equal split)

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
    + CONTRACT_SECONDS / CONTRACT_BLOCK
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


def transfer(contract: float, own: int, partner: int) -> int:
    """Moves the first player gives to the other under the commission-wages rule (slides 11-13).

    `own` and `partner` are the points each one collected. Commission keeps (1 - contract) of
    your own; wages pool the rest of both and split the pot equally. Together that is one
    transfer of contract * (own - partner) / 2 points. It is counted in moves (POINT_MOVES per
    point, an even number) so that full wages always give exactly equal shares; only in-between
    contracts round, to the nearest whole move. static/split_scene.js draws the same rule.
    """
    gap = contract * (own - partner) * POINT_MOVES / 2
    whole = int(abs(gap) + 0.5 + 1e-9)
    return whole if gap >= 0 else -whole


def split(contract: float, own: int, partner: int) -> int:
    """Moves the first player gets from the points both collected."""
    return own * POINT_MOVES - transfer(contract, own, partner)


def signed(n: int) -> str:
    return f"+ {n}" if n > 0 else (f"− {-n}" if n < 0 else "0")


def contract_label(contract: float) -> str:
    return f"{round(100 * (1 - contract))}% commission / {round(100 * contract)}% wages"


def points(n: int) -> str:
    return f"{n} point" if n == 1 else f"{n} points"


def moves(n: int) -> str:
    return f"{n} move" if n == 1 else f"{n} moves"


def points_collected(participant: Participant) -> int:
    """Points reported by the board page (clamped: the answer comes from the browser)."""
    answer = last_valid_answer(participant, "foraging_page")
    raw = answer.get("coins_collected", 0) if isinstance(answer, dict) else 0
    return int(min(max(_as_float(raw), 0), GRID_SIZE * GRID_SIZE))


def moves_invested(participant: Participant) -> int:
    """The invest-slider answer, kept within what the slider allowed (the browser sends it)."""
    top, _ = invest_slider(bank(participant))
    step = MOVE_STEP if top >= MOVE_STEP else 1
    raw = int(min(max(_as_float(last_valid_answer(participant, "buy_moves")), 0), top))
    return raw - raw % step


def bank(participant: Participant) -> int:
    """Moves carried over: the starting bank plus every finished round."""
    return START_MOVES + sum(participant.var.get("scores", {}).values())


def results(participant: Participant) -> list:
    return participant.var.get("results", [])


def is_out(participant: Participant) -> bool:
    return participant.var.get("out_round", None) is not None


def is_solo(participant: Participant) -> bool:
    return participant.var.get("partner_out_round", None) is not None


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
    collected = {p.id: points_collected(p) for p in players}
    for i, p in enumerate(players):
        if not solo:
            p.var.set("color_index", i)  # as on the board, where colours follow participant IDs
        others = [q for q in players if q.id != p.id]
        own = collected[p.id]
        other = collected[others[0].id] if others else 0
        gained = own * POINT_MOVES if solo else split(contract, own, other)
        food = FOOD_MOVES * (SOLO_FOOD_FACTOR if solo else 1)
        invested = moves_invested(p)
        score = gained - invested - food
        round_number = len(results(p)) + 1
        result = dict(
            round=round_number, solo=solo, contract=None if solo else contract,
            own=own, other=other, gained=gained, invested=invested, food=food, score=score,
        )
        p.var.set("results", results(p) + [result])
        scores = p.var.get("scores", {})
        scores[str(round_number)] = score
        p.var.set("scores", scores)
    for p in players:
        if bank(p) <= 0:
            p.var.set("out_round", len(results(p)))
            # The partner plays on alone: the group must not wait for a second player, and
            # nobody new may join it mid-game.
            group.min_group_size = 1
            group.accepts_top_ups = False
            group.remove_participant(p)
            for q in players:
                if q.id != p.id and bank(q) > 0:
                    q.var.set("partner_out_round", len(results(q)))


def average_proposals(group, participants, participant, barrier):
    """Runs when both players have proposed: the next contract is their average."""
    proposals = [
        _as_float(last_valid_answer(p, "propose_contract"), None) for p in participants
    ]
    proposals = [p for p in proposals if p is not None]
    if proposals:
        # The exact average (it can fall between the slider's 10% marks, e.g. 5%).
        group.var.set("contract", sum(proposals) / len(proposals))


def slider_preview(slider_id: str, output_id: str, js_body: str) -> str:
    """Live text next to a slider; `v` is the current slider value.

    Runs on trialConstruct because the PsyNet slider control is rendered after the prompt.
    """
    return f"""
        <div id="{output_id}" class="live-value"></div>
        <script>
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
            <p>Everything in this game is counted in <strong>moves</strong>. You start with
            <strong>{START_MOVES} moves</strong> in your bank and play up to <strong>{N_ROUNDS}
            rounds</strong> with a partner, each on a new board. Each round:</p>
            <ol>
                <li><strong>Invest moves</strong> from your bank: they are the steps your
                    pac-man can take.</li>
                <li><strong>Collect points</strong> on a dark board.</li>
                <li><strong>Share the points</strong> with the contract. The game turns them into
                    moves for you and pays for food.</li>
            </ol>
            <p>Every {CONTRACT_BLOCK} rounds you and your partner propose a new contract.
            If your bank runs out, you are out of the game.</p>
            """
        ),
        time_estimate=TUTORIAL_SECONDS,
    )


def colors(participant: Participant) -> tuple:
    """The pac-man colours of this player and their partner, as on the board."""
    me = participant.var.get("color_index", 0)
    return PLAYER_COLORS[me], PLAYER_COLORS[1 - me]


def invest_slider(have: int) -> tuple:
    """Largest investment and number of slider stops, never more than the bank.

    The slider moves in steps of MOVE_STEP; with fewer than MOVE_STEP moves in the bank it
    moves one by one, so that those last moves can still be invested.
    """
    if have >= MOVE_STEP:
        top = min(MAX_MOVES, have - have % MOVE_STEP)
        return top, top // MOVE_STEP + 1
    return max(have, 1), max(have, 1) + 1


def buy_moves_page(participant: Participant, round_index: int) -> ModularPage:
    have = bank(participant)
    top, n_stops = invest_slider(have)
    if is_solo(participant):
        situation = (
            f"Your partner ran out of moves, so you play <strong>alone</strong>: no contract, and "
            f"food costs {FOOD_MOVES * SOLO_FOOD_FACTOR} moves. You can play at most "
            f"{SOLO_MAX_ROUNDS - solo_rounds(participant)} more rounds."
        )
    else:
        situation = (
            f"Contract: <strong>{contract_label(current_contract(participant))}</strong>. "
            f"Food costs {FOOD_MOVES} moves each round."
        )
    preview = slider_preview(
        "moves-slider",
        "moves-output",
        f"""
        out.innerHTML = "You invest <strong>" + v + (v === 1 ? " move" : " moves")
            + "</strong>; " + ({have} - v) + " stay in your bank";
        """,
    )
    prompt = Markup(
        f"""
        <h3>Round {round_index + 1} of {N_ROUNDS}: invest moves</h3>
        <p>You have <strong>{have} moves</strong> in your bank. <strong>How many do you want to
        invest in this round?</strong> They are the steps your pac-man can take. After the round,
        the points are shared with the contract and turned into moves ({POINT_MOVES} per point).</p>
        <p>{situation}</p>
        {preview}
        {slider_frame("moves-slider", "0 moves", f"{top} moves", n_stops, below="moves-output")}
        """
    )
    return ModularPage(
        "buy_moves",
        Prompt(prompt),
        SliderControl(
            start_value=min(20, top),
            min_value=0,
            max_value=top,
            n_steps=n_stops,
            slider_id="moves-slider",
            minimal_interactions=1,
            bot_response=min(30, top),
        ),
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
            <strong>{points(r["other"])}</strong>. Watch the contract
            (<strong>{contract_label(r["contract"])}</strong>) share them:</p>
            {scene}
        """
    if is_out(participant):
        tail = """<p class="out-note"><strong>Your bank is empty: you are out of the game.</strong>
                  """ + ("" if r["solo"] else "Your partner continues alone.") + "</p>"
    elif participant.var.get("partner_out_round", None) == r["round"]:
        tail = f"""<p class="out-note"><strong>Your partner ran out of moves.</strong> From now on
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
        <h3>Propose a new contract</h3>
        <p>The last {CONTRACT_BLOCK} rounds used <strong>{contract_label(contract)}</strong>.
        Move the slider to propose the contract for the <strong>next {CONTRACT_BLOCK} rounds</strong>.
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
            minimal_interactions=1,
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
    elif is_solo(participant):
        how = (f"Your partner ran out of moves in round {participant.var.get('partner_out_round')}; "
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
        # Barrier IDs are scoped by node: both players share it, and each round has its own.
        return join(
            PageMaker(
                lambda participant: buy_moves_page(participant, round_index),
                time_estimate=MOVES_SECONDS,
            ),
            crew_barrier(
                f"moves_{self.node_id}",
                "Waiting for your partner to finish investing moves...",
            ),
            PageMaker(
                lambda participant: ForagingPage(
                    participant,
                    round_id=self.node_id,
                    moves=moves_invested(participant),
                    title=f"<h3>Round {round_index + 1} of {N_ROUNDS}: collect points</h3>",
                    terrain=ROUND_TERRAINS[round_index % len(ROUND_TERRAINS)],
                ),
                time_estimate=FORAGING_DURATION,
            ),
            crew_barrier(
                f"foraging_{self.node_id}",
                "Waiting for your partner to finish the round...",
                on_release=score_round,
            ),
            PageMaker(score_page, time_estimate=SCORE_SECONDS),
            # Players who are out, or alone, do not propose (and must not wait at a barrier).
            conditional(
                f"propose_{round_index}",
                lambda participant: (
                    proposes_after(round_index)
                    and not is_out(participant)
                    and not is_solo(participant)
                ),
                join(
                    PageMaker(propose_contract_page, time_estimate=CONTRACT_SECONDS),
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

    @staticmethod
    def game_over(participant: Participant) -> bool:
        return is_out(participant) or solo_rounds(participant) >= SOLO_MAX_ROUNDS

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
            min_group_size=MIN_PLAYERS,
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
        max_pages = 400
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
        n = len(bot.var.get("scores", {}))
        assert 1 <= n <= N_ROUNDS
        assert len(bot.var.get("results", [])) == n
