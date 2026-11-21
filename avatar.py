"""Pac-man avatars: each player chooses a colour, a hat and eyes, and sees everyone else in disguise.

A participant picks them before the lobby. They always see their own
pac-man as they chose it. Every other pac-man they see is drawn at random, and redrawn
each round, so nobody can tell who they met before: the group stays anonymous, and with
eight players it still looks like many different people (Andrade, meeting of 10-nov).

static/pacman_avatar.js draws the same options; keep the two lists in step.
"""

import hashlib
import random
from typing import Dict, Iterable

from psynet.participant import Participant

# Okabe-Ito colours, which stay apart for the common kinds of colour blindness. Black is
# swapped for white (the board is dark) and the blue is lighter, so it shows on the board.
# See agent-reports 2026-11-17/avatares-pacman for the measurements.
AVATAR_COLORS = {
    "yellow": "#F0E442",
    "orange": "#E69F00",
    "red": "#D55E00",
    "sky": "#56B4E9",
    "blue": "#3D7FE0",
    "green": "#009E73",
    "pink": "#CC79A7",
    "white": "#F2F2F2",
}
# Only pac-men (Andrade, 20-nov: no ghosts). The field stays so the saved answer keeps its shape.
AVATAR_BODIES = ["pacman"]
# One hat per other player in a full group of eight (seven), plus none.
AVATAR_HATS = ["none", "cap", "top_hat", "crown", "party", "beanie", "cowboy", "viking", "bow"]
# After emojis: classic, happy ^ (😊), wink (😉), sunglasses (😎), hearts (😍).
AVATAR_EYES = ["dot", "happy", "wink", "cool", "hearts"]

DEFAULT_AVATAR = {"body": "pacman", "color": "yellow", "hat": "none", "eyes": "dot"}

# Open decision (reputation, meeting of 10-nov): False keeps the group anonymous, with everyone
# else in a disguise that changes each round. True shows every player as they chose, so a
# partner can be recognised from round to round.
SHOW_CHOSEN_AVATARS = True

# Changing it reshuffles every disguise; it only has to stay fixed during a session.
_SALT = "pacmans-cave"


def clean_avatar(raw) -> dict:
    """An avatar with only known options. Anything unknown falls back to the default."""
    raw = raw if isinstance(raw, dict) else {}
    return {
        "body": raw.get("body") if raw.get("body") in AVATAR_BODIES else DEFAULT_AVATAR["body"],
        "color": raw.get("color") if raw.get("color") in AVATAR_COLORS else DEFAULT_AVATAR["color"],
        "hat": raw.get("hat") if raw.get("hat") in AVATAR_HATS else DEFAULT_AVATAR["hat"],
        "eyes": raw.get("eyes") if raw.get("eyes") in AVATAR_EYES else DEFAULT_AVATAR["eyes"],
    }


def starting_avatar(participant: Participant) -> dict:
    """The avatar the picker opens with: the colour follows the participant id, so players
    who join one after another each start with a different colour."""
    colors = list(AVATAR_COLORS)
    return dict(DEFAULT_AVATAR, color=colors[int(participant.id) % len(colors)])


def own_avatar(participant: Participant) -> dict:
    return clean_avatar(participant.var.get("avatar", None))


def random_avatar(rng: random.Random) -> dict:
    return {
        "body": rng.choice(AVATAR_BODIES),
        "color": rng.choice(list(AVATAR_COLORS)),
        "hat": rng.choice(AVATAR_HATS),
        "eyes": rng.choice(AVATAR_EYES),
    }


def _rng(*parts) -> random.Random:
    """A generator that gives the same draws for the same parts, in any process."""
    key = ":".join(str(p) for p in (_SALT,) + parts)
    return random.Random(int(hashlib.sha256(key.encode()).hexdigest()[:16], 16))


def disguises(viewer: Participant, others: Iterable[int], round_key) -> Dict[str, dict]:
    """How ``viewer`` sees each of ``others`` in round ``round_key``.

    Colours differ from the viewer's own, and colours and hats differ from each other while
    the lists last, so nobody looks like you and, with up to eight players, no two others
    share a colour or a hat: the hat tells them apart when colours are hard to see. The draw
    depends only on the viewer and the round, so a reload, the board and the score page agree.
    """
    mine = own_avatar(viewer)["color"]
    palette = [c for c in AVATAR_COLORS if c != mine]
    hats = list(AVATAR_HATS)
    rng = _rng(viewer.id, round_key)
    rng.shuffle(palette)
    rng.shuffle(hats)
    shown = {}
    for i, pid in enumerate(sorted(int(p) for p in others if int(p) != int(viewer.id))):
        look = random_avatar(_rng(viewer.id, round_key, pid))
        look["color"] = palette[i % len(palette)]
        look["hat"] = hats[i % len(hats)]
        shown[str(pid)] = look
    return shown


def avatars_for(viewer: Participant, player_ids: Iterable[int], round_key) -> Dict[str, dict]:
    """Every player in ``player_ids`` as ``viewer`` sees them: themself as chosen, others disguised
    (or as they chose, when SHOW_CHOSEN_AVATARS is on)."""
    ids = [int(p) for p in player_ids]
    if SHOW_CHOSEN_AVATARS:
        found = {int(p.id): p for p in Participant.query.filter(Participant.id.in_(ids)).all()}
        return {str(i): own_avatar(found[i]) if i in found else dict(DEFAULT_AVATAR) for i in ids}
    shown = disguises(viewer, ids, round_key)
    if int(viewer.id) in ids:
        shown[str(viewer.id)] = own_avatar(viewer)
    return shown


def hex_color(avatar: dict) -> str:
    return AVATAR_COLORS[clean_avatar(avatar)["color"]]


# ---- The page where each participant makes their pac-man ----

from markupsafe import Markup  # noqa: E402
from psynet.modular_page import Control, ModularPage  # noqa: E402
from psynet.timeline import PageMaker  # noqa: E402

AVATAR_PAGE_SECONDS = 30


class AvatarControl(Control):
    macro = "avatar_picker"
    external_template = "avatar.html"

    def __init__(self, initial: dict = None):
        super().__init__()
        self.initial = clean_avatar(initial)

    def format_answer(self, raw_answer, **kwargs):
        return clean_avatar(raw_answer)

    def get_bot_response(self, experiment, bot, page, prompt):
        return random_avatar(random.Random())


def avatar_page() -> PageMaker:
    """Choose a colour, a hat and eyes. The answer is kept as ``participant.var.avatar``."""
    return PageMaker(_avatar_page, time_estimate=AVATAR_PAGE_SECONDS)


def _avatar_page(participant: Participant) -> ModularPage:
    return ModularPage(
        "avatar",
        Markup(
            """
            <h3>Make your pac-man</h3>
            <p>Choose a colour, a hat and eyes. You will always see your pac-man like this,
            with a white ring around it on the board.</p>
            """
            + (
                "<p>The other players see your pac-man as you made it.</p>"
                if SHOW_CHOSEN_AVATARS
                else "<p>The other players will not see your choices: to them, and to you, "
                "everyone else looks different in every round.</p>"
            )
        ),
        AvatarControl(initial=starting_avatar(participant)),
        time_estimate=AVATAR_PAGE_SECONDS,
        save_answer="avatar",
        requires_full_page_reload=True,  # the picker uses inline <style> and <script>
    )
