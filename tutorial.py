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
    MAX_MOVES,
    MOVE_PRICE,
    PLAYER_COLORS,
    VARIANT,
    VIEW_RADIUS,
)

TUTORIAL_SECONDS = 60
CONTRACT_ENDS = ("Commission<small>keep what you collect</small>", "Wages<small>equal split</small>")


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
        <h3>Tutorial 1 of 3: buying moves</h3>
        <p>At the start of each round you choose <strong>how many moves</strong> to buy for your
        pac-man. Follow the yellow box on the right.</p>
        {range_input("tut-moves", MAX_MOVES, 1, 5)}
        <div id="tut-moves-out" class="live-value"></div>
        {slider_frame("tut-moves", "0 moves", f"{MAX_MOVES} moves", MAX_MOVES + 1, below="tut-moves-out")}
        <script>
        (function () {{
            var slider = document.getElementById("tut-moves");
            function show() {{
                var v = parseInt(slider.value, 10), cost = v * {MOVE_PRICE};
                document.getElementById("tut-moves-out").innerHTML = "<strong>" + v + " moves</strong> cost <strong>"
                    + cost + " point" + (cost === 1 ? "" : "s") + "</strong>";
            }}
            slider.addEventListener("input", show);
            show();
        }})();
        </script>
    """))
    top_cost = MAX_MOVES * MOVE_PRICE
    steps = [
        dict(type="info", text=f"Practice only: nothing here changes your earnings.<br>"
             f"You can buy up to <strong>{MAX_MOVES} moves</strong>. "
             f"Each move costs <strong>{MOVE_PRICE} points</strong>."),
        dict(type="slider", slider="tut-moves", target=0,
             text="Move the slider to <strong>0 moves</strong>, then click Check.",
             hint="Drag the slider all the way to the left.",
             explanation="With 0 moves you pay nothing, but you stay still all round."),
        dict(type="slider", slider="tut-moves", target=MAX_MOVES,
             text=f"Now move it to <strong>{MAX_MOVES} moves</strong>, the most you can buy.",
             hint="Drag the slider all the way to the right.",
             explanation=f"{MAX_MOVES} moves cost {top_cost} points."),
        dict(type="slider", slider="tut-moves", target=4,
             text="Now buy <strong>4 moves</strong>.",
             hint="Watch the text under the slider until it says 4 moves.",
             explanation=f"4 moves cost {4 * MOVE_PRICE} points."),
        quiz("You buy 6 moves. How many points do they cost?",
             ["1", str(6 * MOVE_PRICE), "15"], 1,
             f"Each move costs {MOVE_PRICE} points, so 6 moves cost {6 * MOVE_PRICE} points.",
             hint=f"Each move costs {MOVE_PRICE} points."),
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
    moves = 4
    me = dict(x=4, y=4, color=PLAYER_COLORS[0], coins=0, moves_left=moves,
              trajectory=[[4, 4]], connected=True)
    partner = dict(x=8, y=8, color=PLAYER_COLORS[1], coins=0, moves_left=0,
                   trajectory=[[8, 5], [8, 6], [8, 7], [8, 8]], connected=True)
    prompt = PracticeBoardPrompt(
        """<h3>Tutorial 2 of 3: moving and finding coins</h3>
        <p>This is a practice board. Follow the yellow box on the right.</p>""",
        players={"0": me, "1": partner},
        coins=[{"id": 0, "x": 5, "y": 4}, {"id": 1, "x": 7, "y": 4}],
        moves=moves,
    )
    steps = [
        dict(type="info", text="Your pac-man is the one with the <strong>white ring</strong>. "
             "The other pac-man is your partner. (Colours can change in the real game; "
             "the white ring is always you.)"),
        dict(type="board", check="me.x === 5 && me.coins === 1",
             text="There is a coin just to your right. Press the <strong>Right arrow</strong> "
             "(or D) once to pick it up.",
             hint="If you pressed another key, click Restart this step.",
             explanation="Moving onto a coin collects it. That move used 1 of your 4 moves."),
        dict(type="board", check="me.x === 6",
             text="You only see coins in the <strong>3×3 squares around you</strong>; the dark "
             "squares may hide coins. Press <strong>Right</strong> again and watch a new coin appear.",
             hint="If you pressed another key, click Restart this step.",
             explanation="Coins appear when they are next to you."),
        dict(type="board", check="me.x === 4 && me.moves_left === 0",
             text="Press <strong>Left</strong> twice to go back. Look at the coloured squares: "
             "they show where each of you has been.",
             hint="If you pressed another key, click Restart this step.",
             explanation="You used all 4 moves. With no moves left you cannot move any more."),
        quiz("What can you see while you move?",
             ["Every coin on the board", "Coins next to you, your partner and both trails",
              "Only your own pac-man"], 1,
             "Coins show only in the 3×3 squares around you; your partner and both trails are "
             "always visible.",
             hint="Look at the practice board: which coins could you see?"),
        quiz("You have no moves left but your partner still has some. What happens?",
             ["You can keep moving", "You stop; your partner can keep moving",
              "The round ends for both of you"], 1,
             f"You stop. The round ends when time runs out ({FORAGING_DURATION} s), when all "
             "coins are taken, or when both of you have no moves left.",
             hint="Each player has their own moves."),
    ]
    return tutorial_page("tutorial_board", prompt, steps)


def contract_tutorial(split_js: str, split_parts, fixed_cost: int, coin_points: int) -> ModularPage:
    # Slides 11-13: 11 and 5 coins. With coin_points a multiple of 20 every part is whole.
    my_coins, their_coins = 11, 5
    mine, theirs = my_coins * coin_points, their_coins * coin_points
    prompt = Prompt(Markup(f"""
        <h3>Tutorial 3 of 3: splitting the points</h3>
        <p>Each coin is worth <strong>{coin_points} points</strong>. After each round the points of
        both players are divided with a <strong>contract</strong> that mixes two rules:</p>
        <ul>
            <li><strong>Commission</strong>: you keep the points of the coins <em>you</em> collected.</li>
            <li><strong>Wages</strong>: all points go into a common pot that is split <em>equally</em>.</li>
        </ul>
        <p style="text-align:center;font-size:1.1rem">Example: <strong>you collected {my_coins} coins
        ({mine} points)</strong>, <strong>your partner collected {their_coins} coins ({theirs} points)</strong>.</p>
        {range_input("tut-contract", 1, 0.1, 0.3)}
        <div id="tut-contract-out"></div>
        {slider_frame("tut-contract", *CONTRACT_ENDS, 11, below="tut-contract-out")}
        <script>
        {split_js}
        (function () {{
            var slider = document.getElementById("tut-contract");
            function show() {{
                document.getElementById("tut-contract-out").innerHTML =
                    splitTable(parseFloat(slider.value), {mine}, {theirs});
            }}
            slider.addEventListener("input", show);
            show();
        }})();
        </script>
    """))
    keep_half, pot_half, half = split_parts(0.5, mine, theirs)
    partner_half = split_parts(0.5, theirs, mine)[2]
    wages_each = split_parts(1, mine, theirs)[2]
    moves = 12
    earned = half - moves * MOVE_PRICE - fixed_cost
    steps = [
        dict(type="info",
             text="The table under the slider shows the division. First, each player keeps the "
             "<strong>commission</strong> part of their own points. The <strong>wages</strong> part of "
             "both players goes into a pot, and the pot is split in two equal halves."),
        dict(type="slider", slider="tut-contract", target=0,
             text="Move the slider all the way <strong>left, to Commission</strong>, then click Check.",
             hint="Drag the slider all the way to the left.",
             explanation=f"With 100% commission nothing goes to the pot: you keep your {mine} points "
             f"and your partner keeps {theirs}."),
        dict(type="slider", slider="tut-contract", target=1,
             text="Now move it all the way <strong>right, to Wages</strong>.",
             hint="Drag the slider all the way to the right.",
             explanation=f"With 100% wages all {mine + theirs} points go to the pot: {wages_each} each."),
        dict(type="slider", slider="tut-contract", target=0.5,
             text="Now put it in the <strong>middle (50% commission, 50% wages)</strong>.",
             hint="The middle is 50% commission / 50% wages.",
             explanation=f"You keep half of your points ({keep_half}) and get half of the pot "
             f"({pot_half}): {half} points. Your partner gets {partner_half}."),
        quiz("With 50% commission and 50% wages, how many points do you get in this example?",
             [str(mine), str(wages_each), str(half)], 2,
             f"You keep {keep_half} and get {pot_half} from the pot: {keep_half} + {pot_half} = {half}.",
             hint="Put the slider in the middle and read the last row of the table."),
        quiz(f"Your share is {half} points. You bought {moves} moves ({moves * MOVE_PRICE} points) and "
             f"food costs {fixed_cost} points. How many points do you earn this round?",
             [str(earned), str(half - moves * MOVE_PRICE), str(half)], 0,
             f"Your share minus moves and food: {half} − {moves * MOVE_PRICE} − {fixed_cost} = {earned}.",
             hint="Subtract the moves and the food from your share."),
        dict(type="slider", slider="tut-contract", target=0.8,
             text="At the end of each round you <strong>propose</strong> the contract for the NEXT "
             "round. Practise it: propose <strong>80% wages</strong> (one step left of Wages).",
             hint="80% wages is one step to the left of the right end.",
             explanation="Your partner proposed 20% wages. The next round uses the average: 50% wages."),
        # Slide 14: the new value is the average of both proposals (the condition used here).
        quiz("How is the contract for the next round chosen?",
             ["The richer player decides", "The average of both proposals",
              "It stays the same"], 1,
             "It is the average of your proposal and your partner's proposal.",
             hint="Read the last instruction again: what did your partner propose?"),
        quiz("Which round does your proposal change?",
             ["The round that just ended", "The next round"], 1,
             "Only the next round. The points of the round that just ended do not change.",
             hint="The proposal is for the future."),
    ]
    return tutorial_page("tutorial_contract", prompt, steps)
