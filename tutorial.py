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
CONTRACT_ENDS = ("Commission<small>keep what you collect</small>", "Wages<small>share equally</small>")


class TutorialControl(NullControl):
    macro = "tutorial_steps"
    external_template = "tutorial.html"

    def __init__(self, steps: list):
        super().__init__()
        self.steps = steps
        self.show_next_button = False

    def get_bot_response(self, experiment, bot, page, prompt):
        return {"passed": True, "mistakes": 0}


def tutorial_page(label: str, prompt, steps: list) -> ModularPage:
    return ModularPage(
        label,
        prompt,
        TutorialControl(steps),
        time_estimate=TUTORIAL_SECONDS,
        show_next_button=False,
    )


def quiz(question: str, options: list, correct: int, explanation: str, hint: str = "") -> dict:
    return dict(type="quiz", text=f"<strong>{question}</strong>", options=options,
                correct=correct, explanation=explanation, hint=hint)


def slider_frame(slider_id: str, left: str, right: str, n_steps: int, below: str = "") -> str:
    """Ticks and end labels under a slider; optionally move a live value (`below`) under them.

    Shared by the game pages and the tutorials so every slider looks the same. PsyNet renders
    its slider after the prompt, so the frame is moved next to the slider once it exists.
    """
    ticks = "".join(
        f'<span style="left:{100 * i / (n_steps - 1):.4f}%"></span>' for i in range(n_steps)
    )
    return f"""
        <div id="{slider_id}-frame">
            <div class="slider-ticks">{ticks}</div>
            <div class="slider-ends"><span>{left}</span><span>{right}</span></div>
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
    bank = 6  # practice bank, in points (Andrade's sketch: food -> moves)
    prompt = Prompt(Markup(f"""
        <h3>Tutorial 1 of 3: points and moves</h3>
        <p>Your <strong>bank</strong> keeps the points you collect: they are your food. Each round
        you choose how many to invest, and <strong>each point becomes {FOOD_CONVERSION} moves</strong>,
        the steps your pac-man can take. Try the slider.</p>
        <div id="tut-convert"></div>
        <script src="/static/convert_scene.js"></script>
        {range_input("tut-moves", bank, 1, 2)}
        <div id="tut-moves-out" class="live-value"></div>
        {slider_frame("tut-moves", "0 points", f"{bank} points", bank + 1, below="tut-moves-out")}
        <script>
        (function () {{
            var slider = document.getElementById("tut-moves");
            var convert = ConvertScene(document.getElementById("tut-convert"),
                                       {{bank: {bank}, perPoint: {FOOD_CONVERSION}}});
            function show(animate) {{
                var v = parseInt(slider.value, 10);
                convert.set(v, animate);
                document.getElementById("tut-moves-out").innerHTML = "You invest <strong>" + v
                    + (v === 1 ? " point" : " points") + "</strong>: " + v * {FOOD_CONVERSION}
                    + " moves this round; " + ({bank} - v) + " stay in your bank";
            }}
            slider.addEventListener("input", function () {{ show(true); }});
            show(false);
        }})();
        </script>
    """))
    steps = [
        dict(type="info", text="Practice only: nothing here changes your bank.<br>"
             "Moves you don't use are spent anyway. After each round your share of the points "
             "goes to your bank, and you pay some for food. The game counts for you.<br>"
             "If your bank runs out, you leave the game and your partner goes on alone."),
    ]
    return tutorial_page("tutorial_moves", prompt, steps)


class PracticeBoardPrompt(Prompt):
    """The real board template, played locally (no partner, no server)."""

    macro = "foraging_board"
    external_template = "custom-prompts.html"

    def __init__(self, text: str, players: dict, coins: list, moves: int):
        super().__init__(text=Markup(text))
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


def moving_tutorial() -> ModularPage:
    """Andrade, 13-oct: the real 16x16 board in the dark, 80 moves, one point in the centre.
    Collecting it ends the tutorial."""
    moves = 80
    centre = GRID_SIZE // 2
    me = dict(x=1, y=1, color=PLAYER_COLORS[0], coins=0, moves_left=moves,
              trajectory=[[1, 1]], connected=True)
    partner = dict(x=GRID_SIZE - 2, y=GRID_SIZE - 2, color=PLAYER_COLORS[1], coins=0, moves_left=0,
                   trajectory=[[GRID_SIZE - 2, GRID_SIZE - 5 + k] for k in range(4)], connected=True)
    prompt = PracticeBoardPrompt(
        """<h3>Tutorial 2 of 3: moving in the cave</h3>
        <p>This is a practice board. Follow the yellow box on the right.</p>""",
        players={"0": me, "1": partner},
        coins=[{"id": 0, "x": centre, "y": centre}],
        moves=moves,
    )
    steps = [
        dict(type="board", check=f"me.x === {centre} && me.y === {centre}",
             text="You are the pac-man with the <strong>white ring</strong>. There is a point in "
             "the <strong>centre</strong> of the cave: go and collect it. Use the arrow keys "
             "(&uarr; &darr; &larr; &rarr;, or W A S D).",
             hint="Points only show up in your torchlight. Head for the middle of the board.",
             explanation="Points only show up in your torchlight. Each step uses one move. You "
             "always see your partner and both trails."),
    ]
    return tutorial_page("tutorial_board", prompt, steps)


def split_scene(scene_id: str, slider_id: str, you: int, partner: int, contract: float,
                you_color: str = PLAYER_COLORS[0], partner_color: str = PLAYER_COLORS[1],
                fixed: bool = False, play_from: float = None) -> str:
    """The split picture (static/split_scene.js): two pac-men and the points each one keeps.

    With a slider it follows the slider; with `play_from` it animates from that contract to
    `contract` when the page opens (the round result).
    """
    return f"""
        <div id="{scene_id}"></div>
        <div id="{scene_id}-caption" class="split-caption"></div>
        <script src="/static/split_scene.js"></script>
        <script>
        (function () {{
            var caption = document.getElementById("{scene_id}-caption");
            var scene = SplitScene(document.getElementById("{scene_id}"), {{
                you: {you}, partner: {partner}, contract: {contract if play_from is None else play_from},
                youColor: "{you_color}", partnerColor: "{partner_color}",
                onChange: function (info) {{ caption.innerHTML = SplitScene.caption(info); }},
            }});
            caption.insertAdjacentHTML("afterend", SplitScene.legend({{
                youColor: "{you_color}", partnerColor: "{partner_color}" }}));
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
    The example has a gap of 8 points so that commission, the middle and wages give 12-4,
    10-6 and 8-8, as on the slides.
    """
    you, partner = 12, 4
    prompt = Prompt(Markup(f"""
        <h3>Tutorial 3 of 3: sharing the points</h3>
        <p>After each round, a <strong>contract</strong> decides how the points you both collected
        are shared. Each point keeps the colour of the pac-man who collected it.</p>
        {split_scene("tut-scene", "tut-contract", you, partner, 0.3)}
        {range_input("tut-contract", 1, 0.1, 0.3)}
        {slider_frame("tut-contract", *CONTRACT_ENDS, 11)}
        <script>
        // Each step can bring a new example ({{example: [you, partner], start: contract}}) and,
        // for a prediction question, show the answer once it is given ({{reveal: contract}}).
        window.addEventListener("tutorial-step", function (event) {{
            var s = event.detail, slider = document.getElementById("tut-contract");
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
    """))

    steps = [
        dict(type="slider", slider="tut-contract", target=1, example=[you, partner], start=0,
             text=f"<strong>You collected {you} points</strong>, <strong>your partner {partner}</strong>. "
             "On <strong>Commission</strong> each keeps their own. Drag the slider to "
             "<strong>Wages</strong> and watch.",
             hint="Drag the slider all the way to the right.",
             explanation="You tried <strong>Wages</strong>: both players get an equal share of all "
             "the points collected. Between the two ends, points are partly shared."),
        dict(quiz(f"Now <strong>your partner collected {you}</strong> and <strong>you "
                  f"{partner}</strong>. If the slider were on Wages, what would happen?",
                  ["Your partner gives you points", "You give your partner points",
                   "No points move"], 0,
                  "Points move from whoever collected more to whoever collected fewer.",
                  hint="With Wages both players end up with the same number of points."),
             example=[partner, you], start=0, reveal=1),
    ]
    return tutorial_page("tutorial_contract", prompt, steps)
