"""Step-by-step tutorial: one page per part of the game (Andrade, 29-sep).

Like the tutorial of EAndrade-Lotero/nested_games: each step asks for one concrete action or
answer, gives Correct/Incorrect feedback, and the page only moves on when every step passes.
Practice never affects earnings.
"""
from markupsafe import Markup
from psynet.modular_page import ModularPage, NullControl, Prompt

from .foraging import (
    EnableForaging,
    FORAGING_DURATION,
    GRID_SIZE,
    PLAYER_COLORS,
    VARIANT,
    VIEW_RADIUS,
)
from .game_parameters import (
    FOOD_CONVERSION,
)

TUTORIAL_SECONDS = 60
# A foraging stage of tutorial 2 passes when the participant collects at least this share of
# the food: sharing it with the partner is fine, collecting very little means they missed the
# point (Thomas, 2-nov: "no tiene que ser exactamente la mitad").
FAIR_SHARE = 0.25
CONTRACT_ENDS = ("0%<small>group contribution</small>", "100%<small>group contribution</small>")


class TutorialControl(NullControl):
    macro = "tutorial_steps"
    external_template = "tutorial.html"

    def __init__(self, steps: list, bare: bool = False, progress_label: str = "Step"):
        super().__init__()
        self.steps = steps
        self.bare = bare  # no instruction box: only the Continue button (the page says what to do)
        self.progress_label = progress_label
        self.show_next_button = False

    def get_bot_response(self, experiment, bot, page, prompt):
        return {"passed": True, "mistakes": 0}


def tutorial_page(label: str, prompt, steps: list, bare: bool = False,
                  progress_label: str = "Step") -> ModularPage:
    return ModularPage(
        label,
        prompt,
        TutorialControl(steps, bare, progress_label),
        time_estimate=TUTORIAL_SECONDS,
        show_next_button=False,
        # tutorial.html has a style block, an inline script, and window
        # listeners. PsyNet 14 refuses to swap that in place.
        requires_full_page_reload=True,
    )


def quiz(question: str, options: list, correct: int, explanation: str, hint: str = "") -> dict:
    return dict(type="quiz", text=f"<strong>{question}</strong>", options=options,
                correct=correct, explanation=explanation, hint=hint)


def slider_frame(slider_id: str, left: str, right: str, n_steps: int, below: str = "",
                 values: list = None) -> str:
    """Ticks and end labels under a slider; optionally move a live value (`below`) under them.

    Shared by the game pages and the tutorials so every slider looks the same. PsyNet renders
    its slider after the prompt, so the frame is moved next to the slider once it exists.
    With `values`, each tick gets its value under it (the current one highlighted) instead of
    the end labels.
    """
    ticks = "".join(  # n_steps=0: no ticks, only the end labels
        f'<span style="left:{100 * i / (n_steps - 1):.4f}%"></span>' for i in range(n_steps)
    ) if n_steps > 1 else ""
    if values:
        labels = "".join(
            f'<span data-v="{v}" style="left:{100 * i / (len(values) - 1):.4f}%">{v}</span>'
            for i, v in enumerate(values)
        )
        under = f'<div class="slider-values">{labels}</div>'
    else:
        under = f'<div class="slider-ends"><span>{left}</span><span>{right}</span></div>'
    return f"""
        <div id="{slider_id}-frame">
            <div class="slider-ticks">{ticks}</div>
            {under}
        </div>
        <script>
        (function () {{
            function place() {{
                var slider = document.getElementById("{slider_id}");
                var frame = document.getElementById("{slider_id}-frame");
                if (!slider) return;
                slider.after(frame);
                var below = document.getElementById("{below}");
                if (below) frame.after(below);
                if (!slider.dataset.values) {{
                    slider.dataset.values = "1";
                    var mark = function () {{
                        frame.querySelectorAll(".slider-values span").forEach(function (label) {{
                            label.classList.toggle("active", label.dataset.v === slider.value);
                        }});
                    }};
                    slider.addEventListener("input", mark);
                    mark();
                }}
            }}
            place();
            if (window.psynet && psynet.trial) psynet.trial.onEvent("trialConstruct", place);
        }})();
        </script>
    """


def range_input(slider_id: str, maximum: float, step: float, value: float) -> str:
    return f'<input type="range" class="form-range" id="{slider_id}" min="0" max="{maximum}" step="{step}" value="{value}">'


def buying_moves_tutorial() -> ModularPage:
    """Investing (critiques of 12-oct): bank vs. this round's steps, unused moves are spent,
    and running out ends your game while your partner plays on. No arithmetic."""
    bank = 6  # practice food bank (Andrade's sketch: food -> moves)
    target = 5  # the participant must invest exactly this much food to continue
    prompt = Prompt(Markup(f"""
        <h3>Tutorial 1 of 3: food and moves</h3>
        <p>This is your <strong>food bank</strong>. Here you can turn food into moves for foraging.
        <strong>Each unit of food is worth {FOOD_CONVERSION} moves.</strong></p>
        <div id="tut-convert" class="scene-box"></div>
        <script src="/static/convert_scene.js"></script>
        {range_input("tut-moves", bank, 1, 0)}  <!-- starts at 0 (Thomas, 2-nov) -->
        <div id="tut-moves-out" class="live-value"></div>
        {slider_frame("tut-moves", "", "", bank + 1, below="tut-moves-out", values=list(range(bank + 1)))}

        <div id="tut-popup" class="tut-popup" role="dialog" aria-modal="true" aria-labelledby="tut-popup-title">
            <div class="tut-popup-card">
                <div class="tut-popup-tag">Practice</div>
                <h4 id="tut-popup-title">Invest {target} food</h4>
                <p style="margin-bottom:1.1em">Move the slider to invest <strong>{target} food</strong>
                and watch it turn into moves.</p>
                <button type="button" class="btn btn-primary" id="tut-popup-ok">OK</button>
            </div>
        </div>
        <style>
            #tut-moves-out {{ font-weight: 400; }}
            #tut-moves-out.done {{ color: #1e7b34; }}
        </style>
        <script>
        (function () {{
            var popup = document.getElementById("tut-popup");
            document.getElementById("tut-popup-ok").addEventListener("click", function () {{
                popup.hidden = true;
                document.getElementById("tut-moves").focus();
            }});
            var slider = document.getElementById("tut-moves");
            var convert = ConvertScene(document.getElementById("tut-convert"),
                                       {{bank: {bank}, perPoint: {FOOD_CONVERSION}}});
            var out = document.getElementById("tut-moves-out");
            function show(animate) {{
                var v = parseInt(slider.value, 10);
                convert.set(v, animate);
                // The instruction again, under the slider; a tick once it is done.
                var done = v === {target};
                out.classList.toggle("done", done);
                out.innerHTML = "<em>" + (done ? "&#10003; " : "") + "Instruction: Invest {target} food</em>";
            }}
            slider.addEventListener("input", function () {{ show(true); }});
            show(false);
        }})();
        </script>
    """))
    steps = [
        dict(type="slider", slider="tut-moves", target=target,
             text=f"Move the slider to invest <strong>{target} food</strong>.",
             # Continue is always there; pressing it with another amount opens this popup.
             wrong=f"Move the slider to invest <strong>{target} food</strong>, then press Continue.",
             wrong_title="Incorrect investment",
             hint=f"Drag the slider to {target} food.",
             explanation=f"Each unit of food became {FOOD_CONVERSION} moves."),
    ]
    return tutorial_page("tutorial_moves", prompt, steps, bare=True)


class PracticeBoardPrompt(Prompt):
    """The real board template, played locally (no partner, no server)."""

    macro = "foraging_board"
    external_template = "custom-prompts.html"

    def __init__(self, text: str, players: dict, coins: list, moves: int, legend: str = ""):
        super().__init__(text=Markup(text))
        self.legend = Markup(legend)  # replaces the usual line under the board
        self.practice = True
        self.room_id = "practice"
        self.participant_id = 0
        self.known_players = players
        self.coins = coins
        self.moves = moves
        self.terrain = "practice"
        self.grid_size = GRID_SIZE
        self.timer_seconds = FORAGING_DURATION
        self.channel = EnableForaging.channel
        self.style = VARIANT
        self.view_radius = VIEW_RADIUS


def _pawn(x: int, y: int, color: str, moves: int, trajectory: list = None) -> dict:
    return dict(x=x, y=y, color=color, coins=0, moves_left=moves,
                trajectory=[[x, y]] if trajectory is None else trajectory, connected=True)


# A patch shaped like the clusters in the real maps (static/maps/andrade16_map0 and _map1),
# not a perfect square: 16 food.
BLOB = [
    ".##..",
    "####.",
    "#####",
    ".###.",
    "..##.",
]


# Stage 2's patch: a 6x6 square without its corners against the right edge (Thomas, 2-nov),
# 32 food. It is symmetric, so the half facing each player is the same size: the top three
# rows (16 food) face the participant and the bottom three the partner.
LOZENGE = [
    ".####.",
    "######",
    "######",
    "######",
    "######",
    ".####.",
]


def _shape(rows: list, x0: int, y0: int) -> list:
    """The `#` cells of `rows`, with the top-left cell at (x0, y0)."""
    return [(x0 + x, y0 + y) for y, row in enumerate(rows) for x, c in enumerate(row) if c == "#"]


def _blob(x0: int, y0: int, flip: bool = False) -> list:
    """BLOB with its top-left cell at (x0, y0); `flip` turns it half a turn (point symmetry)."""
    cells = [(x, y) for y, row in enumerate(BLOB) for x, c in enumerate(row) if c == "#"]
    side = len(BLOB) - 1
    if flip:
        cells = [(side - x, side - y) for x, y in cells]
    return [(x0 + x, y0 + y) for x, y in cells]


def _coins(cells: list) -> list:
    return [{"id": i, "x": x, "y": y} for i, (x, y) in enumerate(cells)]


# Tutorial 2's prediction question before stage 3 (Thomas, 2-nov: off for now, to propose to
# Andrade).
PREDICTION_QUESTION = False


def moving_tutorial() -> ModularPage:
    """Three stages on the real board (Andrade, 13-oct, plus group-foraging practice).

    Stage 1 is the original task, with a cross of five pieces of food in the centre. Stages 2 and 3 are live
    foraging with a partner bot that walks, one cell at a time, to the closest food (in stage 3,
    in the patch the participant is not heading to). Movement,
    move cost, edges and collecting match the experiment; the bot simply has no keyboard.
    The bot waits for the participant's first move, and a stage ends when the food runs out:
    it passes if the participant collected at least FAIR_SHARE of it, and starts again otherwise.
    """
    moves = 80
    centre = GRID_SIZE // 2
    top_left, top_right = (0, 0), (GRID_SIZE - 1, 0)
    bottom_left, bottom_right = (0, GRID_SIZE - 1), (GRID_SIZE - 1, GRID_SIZE - 1)
    me = _pawn(1, 1, PLAYER_COLORS[0], moves)
    # Stage 1: a cross of five pieces in the centre (Thomas, 2-nov), all to be collected.
    cross = [(centre, centre), (centre - 1, centre), (centre + 1, centre),
             (centre, centre - 1), (centre, centre + 1)]
    centre_coins = _coins(cross)
    # Stage 2 (same patch): one patch against the right edge, nearer the other player
    # (bottom right) than the participant (top left). The other player races for it from the
    # participant's first move, with no pause; it hurries once the participant finds food
    # (Thomas, 2-nov): what one of them eats, the other doesn't.
    # Stage 3 (split): the participant starts bottom left and the partner top right, with a
    # patch in each of the other two corners; the partner takes the one the participant is
    # not heading to. Neither popup says where the food is.
    # Stage 2's patch is symmetric; stage 3's are shaped like the real maps' clusters
    # (Thomas, 2-nov).
    pocket = _shape(LOZENGE, GRID_SIZE - 6, GRID_SIZE // 2 - 3)  # x 10..15, y 5..10
    patches = [top_left, bottom_right]
    # The two patches are each other turned half a turn about the centre, as are the starts.
    split_food = _blob(1, 1) + _blob(GRID_SIZE - 6, GRID_SIZE - 6, flip=True)
    # Stage 3 gives the moves to reach one patch, eat it all and still have slack to explore
    # that side, but not to reach the other patch afterwards (Thomas, 2-nov): the slack stays
    # one short of the gap between the two patches.
    patch_size = len(split_food) // 2
    near, far = split_food[:patch_size], split_food[patch_size:]
    reach = min(abs(x - bottom_left[0]) + abs(y - bottom_left[1]) for x, y in split_food)
    gap = min(abs(x0 - x1) + abs(y0 - y1) for x0, y0 in near for x1, y1 in far)
    split_moves = reach + patch_size + gap - 1  # 13 + 16 + 11 = 40

    def share(food: list) -> int:
        return max(1, round(FAIR_SHARE * len(food)))
    prompt = PracticeBoardPrompt(
        """<h3 id="tut-board-title">Tutorial 2 of 3: moving in the cave</h3>""",
        players={"0": me},  # stage 1 has no partner yet (Thomas, 2-nov)
        coins=centre_coins,
        moves=moves,
        legend='<div class="board-instruction"><em>Instruction: collect the food in the '
               'centre of the cave.</em></div>',
    )

    def board_step(check: str, **extra) -> dict:
        return dict(type="board", check=check, **extra)

    centre_legend = (
        '<div class="board-instruction"><em>Instruction: collect the food in the '
        'centre of the cave.</em></div>'
    )
    search_legend = (
        '<div class="board-instruction"><em>Instruction: search for food.</em></div>'
        '<div id="practice-score" class="practice-score" aria-live="polite"></div>'
    )
    steps = [
        board_step(
            f"me.coins >= {len(cross)}",
            text="Collect the food in the centre of the cave.",
            heading="Tutorial 2 of 3: moving in the cave",
            legend=centre_legend,
            setup={"players": {"0": me}, "coins": centre_coins},
            popup_title="Stage 1 of 3: find the food",
            popup="You are the pac-man with the <strong>white ring</strong>. There is food in "
            "the <strong>centre</strong> of the cave: go and collect all of it. Use the arrow keys "
            "(&uarr; &darr; &larr; &rarr;) or W, A, S, D.",
            wrong_title="You've not collected all the food",
            wrong="It is in the <strong>centre</strong> of the cave.",
            out_of_moves="You ran out of moves, so this step starts again. The food is in the "
            "<strong>centre</strong> of the cave.",
            hint="Food only shows up in your torchlight. Head for the middle of the board.",
            explanation="Unused moves do not carry over to the next round.",
        ),
        board_step(
            f"me.coins >= {share(pocket)}",
            text="Search for food.",
            heading="Tutorial 2 of 3",
            legend=search_legend,
            bot="1",
            # Slower than stage 3's partner (Thomas, 2-nov): at 400 ms someone pressing a key
            # every half second could not reach the share; at 650 ms they can up to ~700 ms a key.
            bot_ms=650,
            # Once the participant finds food too, the other player hurries (Thomas, 3-nov).
            # Simulated naive players still reach the share at up to ~700 ms a key.
            bot_race_ms=450,
            scoreboard={"other": "Other player"},  # no "Food left" (Thomas, 3-nov)
            until_food_gone=True,
            setup={
                "players": {
                    "0": _pawn(*top_left, PLAYER_COLORS[0], moves),
                    "1": _pawn(*bottom_right, PLAYER_COLORS[1], 999),  # the bot never stops early
                },
                "coins": _coins(pocket),
            },
            # Neutral wording: no "rival" or "partner" and no lesson; the participant draws the
            # conclusion from play (Thomas, 3-nov).
            popup_title="Stage 2 of 3: search for food",
            popup="The other pac-man is another player: here the computer, in the game another "
            "person. Use your moves wisely to collect as much food as possible. The stage ends when all the food is gone or when there are no more available moves. "
            "A grey gem marks food that has been eaten.",
            wrong_title="Keep searching",
            wrong="The stage ends when all the food is gone.",
            food_gone="All the food is gone. You collected <strong>{you}</strong> and the other "
            "player <strong>{partner}</strong>. That was too little to go on, so this stage "
            "starts again.",
            out_of_moves="You ran out of moves, so this stage starts again.",
            hint="Food only shows up in your torchlight.",
            explanation="You collected <strong>{you}</strong> and the other player "
            "<strong>{partner}</strong>. Unused moves do not carry over to the next round.",
            bare=True,
        ),
        # Prediction before the split stage (Thomas, 2-nov): stage 3 then lets them check it.
        # Off until Andrade decides whether it is too obvious (PREDICTION_QUESTION).
        *([dict(
            type="quiz",
            progress="Before stage 3",
            text="<strong>Before the last stage: if you and the other player both go to the "
            "same patch, how much food can the two of you collect together?</strong>",
            options=[
                "About one patch: you share it",
                "About two patches",
                "It depends only on how fast you move",
            ],
            correct=0,
            hint="Think of stage 2: what one of you ate, the other didn't.",
            explanation="Together you can't collect more than the patch holds. Now play: this "
            "time the other player is your <strong>partner</strong>, and there are two patches.",
        )] if PREDICTION_QUESTION else []),
        board_step(
            # Nearly all of the patch the participant took: leaving up to 3 is fine (Thomas, 2-nov).
            f"me.coins >= {patch_size - 3}",
            text="Search for food.",
            heading="Tutorial 2 of 3",
            legend=search_legend,
            bot="1",
            bot_ms=400,
            bot_patches=[list(p) for p in patches],
            # The other player mirrors the participant's moves (half a turn about the centre)
            # until the participant crosses the middle of the board, then takes the patch
            # nearest to itself (Thomas, 2 and 3-nov): the lesson is splitting the work.
            bot_mirror=True,
            scoreboard={"other": "Other player"},
            until_food_gone=True,
            setup={
                "players": {
                    "0": _pawn(*bottom_left, PLAYER_COLORS[0], split_moves),
                    "1": _pawn(*top_right, PLAYER_COLORS[1], 999),  # the bot never stops early
                },
                "coins": _coins(split_food),
            },
            popup_title="Stage 3 of 3: search again",
            popup="Search for food again. Use your moves wisely to collect as much food as possible. "
            "The stage ends when all the food is gone or when there are no more available moves.",
            wrong_title="Keep searching",
            wrong="The stage ends when all the food is gone.",
            food_gone="All the food is gone. You collected <strong>{you}</strong> and the other "
            "player <strong>{partner}</strong>. That was too little to go on, so this stage "
            "starts again.",
            out_of_moves="You ran out of moves. You collected <strong>{you}</strong> and the other "
            "player <strong>{partner}</strong>. That was too little to go on, so this stage "
            "starts again.",
            hint="Food only shows up in your torchlight.",
            explanation="You collected <strong>{you}</strong> and the other player "
            "<strong>{partner}</strong>. Unused moves do not carry over to the next round.",
            bare=True,
        ),
    ]
    # Board steps drop the box; the prediction question between them shows it.
    steps[0]["bare"] = True
    return tutorial_page("tutorial_board", prompt, steps, progress_label="Stage")


def split_scene(scene_id: str, slider_id: str, you: int, partner: int, contract: float,
                you_color: str = PLAYER_COLORS[0], partner_color: str = PLAYER_COLORS[1],
                fixed: bool = False, play_from: float = None, whole: bool = False,
                caption: bool = True, legend: bool = True) -> str:
    """The split picture (static/split_scene.js): two pac-men and the points each one keeps.

    With a slider it follows the slider; with `play_from` it animates from that contract to
    `contract` when the page opens (the round result). `legend` is the line under the picture
    explaining the dot colours; the score page leaves it off.
    """
    legend_js = (
        'caption.insertAdjacentHTML("afterend", SplitScene.legend({'
        f'youColor: "{you_color}", partnerColor: "{partner_color}"}}));'
        if legend else ""
    )
    return f"""
        <div id="{scene_id}" class="scene-box"></div>
        <div id="{scene_id}-caption" class="split-caption scene-box"{"" if caption else ' hidden'}></div>
        <script src="/static/split_scene.js"></script>
        <script>
        (function () {{
            var caption = document.getElementById("{scene_id}-caption");
            var scene = SplitScene(document.getElementById("{scene_id}"), {{
                you: {you}, partner: {partner}, contract: {contract if play_from is None else play_from},
                whole: {"true" if whole else "false"},
                youColor: "{you_color}", partnerColor: "{partner_color}",
                onChange: function (info) {{ caption.innerHTML = SplitScene.caption(info); }},
            }});
            {legend_js}
            window["{scene_id}"] = scene;
            {"" if play_from is None else f"setTimeout(function () {{ scene.set({contract}, true); }}, 900);"}
            function follow() {{
                var slider = document.getElementById("{slider_id}");
                if (!slider || slider.dataset.scene) return;
                slider.dataset.scene = "1";
                slider.addEventListener("input", function () {{ scene.set(parseFloat(slider.value), true); }});
                scene.set(parseFloat(slider.value), false);
            }}
            {"" if fixed else 'follow(); if (window.psynet && psynet.trial) psynet.trial.onEvent("trialConstruct", follow);'}
        }})();
        </script>
    """


def contract_tutorial() -> ModularPage:
    """The contract, shown with points that move between the two players (slides 11-13).

    No arithmetic: the participant moves the slider and watches the points change rows.
    Called "group contribution" here (Andrade, 13-oct); 100% is full wages. The slider is
    continuous (0-100%), but points only move when the share reaches a
    whole point: with a gap of 8 that happens at 25, 50, 75 and 100% (11-5, 10-6, 9-7, 8-8).
    No half points, and no ticks under the slider.
    """
    you, partner = 12, 4
    other_you, other_partner = 8, 15  # second example: your partner collected more
    prompt = Prompt(Markup(f"""
        <h3>Tutorial 3 of 3: group contribution</h3>
        <p>In this panel, you will see the value of the Group contribution tax. When set to 0%,
        every player keeps their loot. If set to 100%, all players share the loot in equal parts.</p>
        {split_scene("tut-scene", "tut-contract", you, partner, 0, whole=True, caption=False)}
        <div class="slider-name">Group contribution: <strong id="tut-contract-pct">0%</strong></div>
        {range_input("tut-contract", 1, 0.01, 0)}
        <div id="tut-contract-out" class="live-value"></div>
        {slider_frame("tut-contract", "0%", "100%", 0, below="tut-contract-out")}
        <script>
        // Each step can bring a new example ({{example: [you, partner], start: contract}}) and,
        // for a prediction question, show the answer once it is given ({{reveal: contract}}).
        (function () {{
            var slider = document.getElementById("tut-contract");
            function pct() {{
                document.getElementById("tut-contract-pct").textContent = Math.round(slider.value * 100) + "%";
            }}
            slider.addEventListener("input", pct);
            window.addEventListener("tutorial-step", function () {{ setTimeout(pct, 0); }});
            window.addEventListener("tutorial-passed", function () {{ setTimeout(pct, 0); }});
        }})();
        window.addEventListener("tutorial-step", function (event) {{
            var s = event.detail, slider = document.getElementById("tut-contract");
            // The instruction under the slider belongs to the step that asks for it.
            var out = document.getElementById("tut-contract-out");
            out.innerHTML = s.instruction ? "<em>Instruction: " + s.instruction + "</em>" : "";
            // A prediction is answered before the slider can show it.
            slider.disabled = s.reveal !== undefined;
            if (!s.example) return;
            window["tut-scene"].example(s.example[0], s.example[1]);
            slider.value = s.start;
            window["tut-scene"].set(s.start, false);
        }});
        window.addEventListener("tutorial-passed", function (event) {{
            var s = event.detail, slider = document.getElementById("tut-contract");
            if (s.reveal === undefined) return;
            slider.disabled = false;
            slider.value = s.reveal;
            window["tut-scene"].set(s.reveal, true);
        }});
        </script>
        <div class="learn-more">
            <h4>Learn more about Group Contribution</h4>
            <img src="/static/group_contribution.jpg" alt="At 25% group contribution, part of each player's points is pooled and split equally.">
            <p>Group contribution takes the set percentage from each player's loot, splits it equally, and redistributes it to everyone.</p>
        </div>
    """))

    steps = [
        dict(type="slider", slider="tut-contract", target=1, example=[you, partner], start=0,
             bare=True,  # no box: the instruction is in a popup and under the slider
             text="Set the group contribution slider to 100%.",
             instruction="Set the group contribution slider to 100%.",
             popup_title="Group contribution",
             popup="Set the <strong>group contribution</strong> slider to <strong>100%</strong> "
             "and watch the points.",
             wrong="Set the group contribution slider to <strong>100%</strong>, then press Continue.",
             wrong_title="Incorrect contribution percentage",
             hint="Drag the slider all the way to the right.",
             explanation="At 100% group contribution, both players get an equal share of all the "
             "points collected."),
        # The other case, with different numbers (Andrade, 13-oct): the partner collected more.
        # The participant moves the slider again, now to 35% (one point moves: 9 and 14).
        dict(type="slider", slider="tut-contract", target=0.35,
             example=[other_you, other_partner], start=0, bare=True,
             text="Set the group contribution slider to 35%.",
             instruction="Set the group contribution slider to 35%.",
             popup_title="Group contribution",
             popup="Set the <strong>group contribution</strong> slider to <strong>35%</strong>.",
             wrong="Set the group contribution slider to <strong>35%</strong>, then press Continue.",
             wrong_title="Incorrect contribution percentage",
             hint="Drag the slider to 35%.",
             explanation="At 35% group contribution, part of the points is shared."),
    ]
    return tutorial_page("tutorial_contract", prompt, steps)
