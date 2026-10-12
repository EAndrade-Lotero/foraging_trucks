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
    prompt = Prompt(Markup(f"""
        <h3>Tutorial 1 of 3: investing moves</h3>
        <p>Everything in this game is counted in <strong>moves</strong>. At the start of each round
        you choose <strong>how many moves</strong> to invest from your bank. Follow the yellow box
        on the right.</p>
        {range_input("tut-moves", MAX_MOVES, MOVE_STEP, 10)}
        <div id="tut-moves-out" class="live-value"></div>
        {slider_frame("tut-moves", "0 moves", f"{MAX_MOVES} moves", MAX_MOVES // MOVE_STEP + 1, below="tut-moves-out")}
        <script>
        (function () {{
            var slider = document.getElementById("tut-moves");
            function show() {{
                var v = parseInt(slider.value, 10);
                document.getElementById("tut-moves-out").innerHTML = "You invest <strong>" + v
                    + " moves</strong>: your pac-man can take " + v + " steps";
            }}
            slider.addEventListener("input", show);
            show();
        }})();
        </script>
    """))
    steps = [
        dict(type="info", text=f"Practice only: nothing here changes your bank.<br>"
             f"You start with <strong>{START_MOVES} moves</strong> in your bank. Each round you "
             "invest some of them: they are the <strong>steps your pac-man can take</strong> on "
             "the board."),
        dict(type="slider", slider="tut-moves", target=0,
             text="Move the slider all the way to the left: <strong>0 moves</strong>.",
             hint="Drag the slider all the way to the left.",
             explanation="With 0 moves you keep your bank, but your pac-man cannot move."),
        dict(type="slider", slider="tut-moves", target=MAX_MOVES,
             text=f"Now all the way to the right: <strong>{MAX_MOVES} moves</strong>, the most you "
             "can invest in one round.",
             hint="Drag the slider all the way to the right.",
             explanation="More moves let you explore more of the board, but they cost more."),
        quiz("You invest 40 moves but only use 10. What happens to the other 30?",
             ["They go back to your bank", "They are spent anyway", "Your partner gets them"], 1,
             "Invested moves are spent whether you use them or not, so invest what you plan to use.",
             hint="Investing is like buying fuel before the trip."),
        dict(type="info", text=f"Every point you collect gives you back <strong>{POINT_MOVES} moves"
             "</strong>, and every round you also pay for <strong>food</strong>. Don't worry about "
             "the counting: the game does it for you and shows your bank after each round."),
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
    moves = 12
    me = dict(x=2, y=2, color=PLAYER_COLORS[0], coins=0, moves_left=moves,
              trajectory=[[2, 2]], connected=True)
    partner = dict(x=8, y=8, color=PLAYER_COLORS[1], coins=0, moves_left=0,
                   trajectory=[[8, 5], [8, 6], [8, 7], [8, 8]], connected=True)
    prompt = PracticeBoardPrompt(
        """<h3>Tutorial 2 of 3: moving in the dark</h3>
        <p>This is a practice board. Follow the yellow box on the right.</p>""",
        players={"0": me, "1": partner},
        coins=[{"id": 0, "x": 4, "y": 7}, {"id": 1, "x": 7, "y": 2}],
        moves=moves,
    )
    steps = [
        dict(type="info", text="Your pac-man is the one with the <strong>white ring</strong>; the "
             "other one is your partner.<br>The board is <strong>dark</strong>. You only see the "
             "<strong>lit squares around you</strong>, so points can be hiding anywhere in the dark."),
        dict(type="board", check="me.x === 2 && me.y === 6", target_cell=[2, 6],
             text="Walk to the <strong>orange X</strong> with the arrow keys (or WASD). Watch the "
             "light move with you.",
             hint="If you went the wrong way, click Restart this step.",
             explanation="Each step uses one of your moves, and the light goes with you."),
        dict(type="board", check="me.coins >= 1",
             text="A point is hidden <strong>close to the X</strong>. Look around until you see it, "
             "then step on it to collect it.",
             hint="Try the squares next to you: points only appear when they are lit.",
             explanation="You found it: points appear only when you get close."),
        quiz("What can you see while you move?",
             ["Every point on the board", "Points next to you, your partner and both trails",
              "Only your own pac-man"], 1,
             "Points show only in the lit squares around you; your partner and both trails are "
             "always visible, so you can see where your partner has already searched.",
             hint="Which points could you see on the practice board?"),
        quiz("You have no moves left but your partner still has some. What happens?",
             ["You can keep moving", "You stop; your partner can keep moving",
              "The round ends for both of you"], 1,
             f"You stop. The round ends when time runs out ({FORAGING_DURATION} s), when all "
             "points are taken, or when both of you have no moves left.",
             hint="Each player has their own moves."),
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


def split_picture(you: int, partner: int, contract: float) -> str:
    """A small still of the split scene (rows of points coloured by who collected them)."""
    gap = contract * (you - partner) / 2
    t = int(abs(gap) + 0.5 + 1e-9) * (1 if gap >= 0 else -1)

    def row(label, own, color, received, received_color):
        dots = f'<b style="border-color:{color}"></b>' * own
        dots += f'<b style="border-color:{received_color}"></b>' * received
        return f"<div><em>{label}</em>{dots}</div>"

    y, p = PLAYER_COLORS[0], PLAYER_COLORS[1]
    return ('<span class="split-mini">'
            + row("You", you - max(t, 0), y, max(-t, 0), p)
            + row("Partner", partner - max(-t, 0), p, max(t, 0), y)
            + "</span>")


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
        // Each step can bring a new example: {{example: [you, partner], start: contract}}.
        window.addEventListener("tutorial-step", function (event) {{
            var s = event.detail, slider = document.getElementById("tut-contract");
            if (!s.example) return;
            window["tut-scene"].example(s.example[0], s.example[1]);
            slider.value = s.start;
            window["tut-scene"].set(s.start, false);
        }});
        </script>
    """))

    def picture(contract):
        return split_picture(you, partner, contract)

    steps = [
        dict(type="slider", slider="tut-contract", target=0, example=[you, partner], start=0.3,
             text=f"This round <strong>you collected {you} points</strong> and <strong>your partner "
             f"{partner}</strong>. Move the slider all the way <strong>left, to Commission</strong>.",
             hint="Drag the slider all the way to the left.",
             explanation="With <strong>commission</strong>, everyone keeps what they collected."),
        dict(type="slider", slider="tut-contract", target=1,
             text="Now drag it all the way <strong>right, to Wages</strong>, and watch the points.",
             hint="Drag the slider all the way to the right.",
             explanation="With <strong>wages</strong>, everything is shared equally: you gave 4 points "
             "and both rows reach the dashed line."),
        dict(type="slider", slider="tut-contract", target=0.5,
             text="Now put it <strong>in the middle</strong>.",
             hint="The middle is the sixth mark.",
             explanation="Half way, you give half as many. The closer to Wages, the more even the rows."),
        dict(type="slider", slider="tut-contract", target=1, example=[partner, you], start=0,
             text=f"Now the other case: <strong>you collected {partner}</strong> and <strong>your "
             f"partner {you}</strong>. Drag the slider to <strong>Wages</strong>.",
             hint="Drag the slider all the way to the right.",
             explanation="Now <strong>your partner gives you</strong> points. Wages always move points "
             "from the player who collected more to the one who collected fewer."),
        dict(quiz(f"You collected {you} and your partner {partner}. Which picture shows "
                  "<strong>50% wages</strong>? (You can try it with the slider.)",
                  [picture(1), picture(0), picture(0.5)], 2,
                  "In the middle of the slider you give half of what Wages would give.",
                  hint="Wages make the rows equal; Commission moves nothing; the middle is in between."),
             example=[you, partner], start=0),
        quiz("With <strong>Wages</strong>, who ends up with more points than they collected?",
             ["The player who collected more", "The player who collected fewer", "Nobody"], 1,
             "Commission rewards whoever collects more; wages protect whoever collects fewer.",
             hint="Look at who received glowing points."),
        quiz(f"The contract stays the same for {CONTRACT_BLOCK} rounds. Then you and your partner "
             "each propose one. Which contract is used next?",
             ["The one proposed by the richer player", "The average of the two proposals",
              "The same one again"], 1,
             f"The next {CONTRACT_BLOCK} rounds use the average of your two proposals. After the "
             f"split, the game turns your points into moves for you ({POINT_MOVES} moves per point).",
             hint="Both proposals count the same."),
    ]
    return tutorial_page("tutorial_contract", prompt, steps)
