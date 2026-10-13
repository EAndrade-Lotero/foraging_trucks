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

    def __init__(self, steps: list, bare: bool = False):
        super().__init__()
        self.steps = steps
        self.bare = bare  # no instruction box: only the Continue button (the page says what to do)
        self.show_next_button = False

    def get_bot_response(self, experiment, bot, page, prompt):
        return {"passed": True, "mistakes": 0}


def tutorial_page(label: str, prompt, steps: list, bare: bool = False) -> ModularPage:
    return ModularPage(
        label,
        prompt,
        TutorialControl(steps, bare),
        time_estimate=TUTORIAL_SECONDS,
        show_next_button=False,
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
        {range_input("tut-moves", bank, 1, 2)}
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
        """<h3>Tutorial 2 of 3: moving in the cave</h3>""",
        players={"0": me, "1": partner},
        coins=[{"id": 0, "x": centre, "y": centre}],
        moves=moves,
        legend='<div class="board-instruction"><em>Instruction: collect the food in the '
               'centre of the cave.</em></div>',
    )
    steps = [
        dict(type="board", check=f"me.x === {centre} && me.y === {centre}",
             text="Collect the food in the centre of the cave.",
             popup_title="Find the food",
             popup="You are the pac-man with the <strong>white ring</strong>. There is food in "
             "the <strong>centre</strong> of the cave: go and collect it. Use the arrow keys "
             "(&uarr; &darr; &larr; &rarr;) or W, A, S, D.",
             wrong_title="You've not found the food",
             wrong="It is in the <strong>centre</strong> of the cave.",
             out_of_moves="You ran out of moves, so this step starts again. The food is in the "
             "<strong>centre</strong> of the cave.",
             hint="Food only shows up in your torchlight. Head for the middle of the board.",
             explanation="Food only shows up in your torchlight. Each step uses one move. You "
             "always see your partner and both trails."),
    ]
    return tutorial_page("tutorial_board", prompt, steps, bare=True)


def split_scene(scene_id: str, slider_id: str, you: int, partner: int, contract: float,
                you_color: str = PLAYER_COLORS[0], partner_color: str = PLAYER_COLORS[1],
                fixed: bool = False, play_from: float = None, whole: bool = False,
                caption: bool = True) -> str:
    """The split picture (static/split_scene.js): two pac-men and the points each one keeps.

    With a slider it follows the slider; with `play_from` it animates from that contract to
    `contract` when the page opens (the round result).
    """
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
    Called "group contribution" here (Andrade, 13-oct); 100% is full wages. The slider is
    continuous (0-100%), but points only move when the share reaches a
    whole point: with a gap of 8 that happens at 25, 50, 75 and 100% (11-5, 10-6, 9-7, 8-8).
    No half points, and no ticks under the slider.
    """
    you, partner = 12, 4
    other_you, other_partner = 8, 15  # second example: your partner collected more
    prompt = Prompt(Markup(f"""
        <h3>Tutorial 3 of 3: group contribution</h3>
        <p>In this panel, you can set the percentage of your harvest that will go to the
        <strong>common pool</strong>. The pool is then divided equally between the players.</p>
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
