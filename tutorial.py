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
    PLAYER_COLORS,
    VARIANT,
    VIEW_RADIUS,
)
from .game_parameters import (
    CONTRACT_BLOCK,
    FOOD_MOVES,
    MAX_MOVES,
    MOVE_STEP,
    POINT_MOVES,
    START_MOVES,
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
    prompt = Prompt(Markup(f"""
        <h3>Tutorial 1 of 3: investing moves</h3>
        <p>Everything in this game is counted in <strong>moves</strong>. Your <strong>bank</strong>
        keeps your moves from round to round. At the start of each round you take some out of the
        bank: they are the <strong>steps your pac-man can take in that round</strong>. Try the
        slider, then follow the yellow box on the right.</p>
        {range_input("tut-moves", MAX_MOVES, MOVE_STEP, 10)}
        <div id="tut-moves-out" class="live-value"></div>
        {slider_frame("tut-moves", "0 moves", f"{MAX_MOVES} moves", MAX_MOVES // MOVE_STEP + 1, below="tut-moves-out")}
        <script>
        (function () {{
            var slider = document.getElementById("tut-moves");
            function show() {{
                var v = parseInt(slider.value, 10);
                document.getElementById("tut-moves-out").innerHTML = "You invest <strong>" + v
                    + " moves</strong>: your pac-man can take " + v + " steps this round";
            }}
            slider.addEventListener("input", show);
            show();
        }})();
        </script>
    """))
    steps = [
        dict(type="info", text=f"Practice only: nothing here changes your bank.<br>"
             f"You start with <strong>{START_MOVES} moves</strong> in your bank. Each round you can "
             f"invest up to {MAX_MOVES}, if your bank has them."),
        quiz("You invest some moves for a round but do not use them all. What happens to the "
             "moves you did not use?",
             ["They go back to your bank", "They are spent anyway", "Your partner gets them"], 1,
             "Invested moves are spent whether you use them or not, so invest what you plan to use.",
             hint="Investing is like filling the tank before a trip."),
        quiz("After a round, your bank is empty. What happens?",
             ["You leave the game, and your partner goes on alone",
              "You get new moves", "Both of you leave the game"], 0,
             f"Each round costs <strong>{FOOD_MOVES} moves of food</strong>, and the points you "
             f"collect give you moves back ({POINT_MOVES} per point). The game does the counting "
             "and shows your bank after every round.",
             hint="The bank is what keeps you in the game."),
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
        self.grid_size = 10
        self.timer_seconds = FORAGING_DURATION
        self.channel = EnableForaging.channel
        self.style = VARIANT
        self.view_radius = VIEW_RADIUS


def moving_tutorial() -> ModularPage:
    """Andrade, 6-oct: "move to the X", then "find the point", with the fog front and centre."""
    moves = 40  # plenty: a wrong turn should never leave the tutorial unsolvable
    me = dict(x=2, y=2, color=PLAYER_COLORS[0], coins=0, moves_left=moves,
              trajectory=[[2, 2]], connected=True)
    partner = dict(x=8, y=8, color=PLAYER_COLORS[1], coins=0, moves_left=0,
                   trajectory=[[8, 5], [8, 6], [8, 7], [8, 8]], connected=True)
    prompt = PracticeBoardPrompt(
        """<h3>Tutorial 2 of 3: moving in the dark</h3>
        <p>This is a practice board. Follow the yellow box on the right.</p>""",
        players={"0": me, "1": partner},
        coins=[{"id": 0, "x": 4, "y": 7}],
        moves=moves,
    )
    steps = [
        dict(type="board", check="me.x === 2 && me.y === 6", target_cell=[2, 6],
             text="Your pac-man is the one with the <strong>white ring</strong>. The board is "
             "<strong>dark</strong>: you only see the lit squares around you.<br>Walk to the "
             "<strong>orange X</strong> with the arrow keys (&uarr; &darr; &larr; &rarr;).",
             hint="If you went the wrong way, click Restart this step.",
             explanation="Each step uses one of your moves, and the light goes with you."),
        dict(type="board", check="me.x === 4 && me.y === 7",
             text="A point is hidden <strong>close to the X</strong>. Look around until you see it, "
             "then step on it to collect it.",
             hint="Try the squares next to you: points only appear when they are lit.",
             explanation="You found it: points appear only when you get close."),
        quiz("What can you see during a round?",
             ["Every point on the board",
              "Points in the lit squares around you, plus both pac-men and their trails",
              "Only your own pac-man"], 1,
             "A trail shows where a pac-man has been; it does not reveal hidden points. When you "
             "have no steps left you stop, and your partner may keep moving.",
             hint="Which points could you see on the practice board?"),
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
             text=f"This round <strong>you collected {you} points</strong> and <strong>your partner "
             f"{partner}</strong>. The slider is on <strong>Commission</strong>: each player keeps "
             "what they collected. Drag it to <strong>Wages</strong> and watch the points.",
             hint="Drag the slider all the way to the right.",
             explanation="With <strong>Wages</strong>, both players get an equal share of all the "
             "points collected: 4 of your points moved to your partner."),
        dict(quiz(f"Now <strong>your partner collected {you}</strong> and <strong>you "
                  f"{partner}</strong>. If the slider were on Wages, what would happen?",
                  ["Your partner gives you points", "You give your partner points",
                   "No points move"], 0,
                  "Points move from whoever collected more to whoever collected fewer.",
                  hint="With Wages both players end up with the same number of points."),
             example=[partner, you], start=0, reveal=1),
        dict(quiz(f"Back to <strong>you {you}, your partner {partner}</strong>. With the slider "
                  "<strong>in the middle</strong>, what happens?",
                  ["No points move", "Some points move: half as many as with Wages",
                   "All the points are shared equally"], 1,
                  "In between, part of the way to an equal split. The game always does the counting.",
                  hint="The middle is between keeping everything and sharing equally."),
             example=[you, partner], start=0, reveal=0.5),
        quiz(f"The contract stays the same for {CONTRACT_BLOCK} rounds. Then each of you proposes a "
             "setting, and the game uses the setting <strong>halfway between your two "
             "proposals</strong>. Who decides the next contract?",
             ["Both of us, equally", "The player with more moves in the bank",
              "Only the player who collected more points"], 0,
             "Both proposals count the same. Your proposal only changes the rounds that come next.",
             hint="Read the rule just above the question."),
    ]
    return tutorial_page("tutorial_contract", prompt, steps)
