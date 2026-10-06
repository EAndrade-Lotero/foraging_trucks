import json
import os
import random
import time
from pathlib import Path
from typing import Dict, List

import gevent
from markupsafe import Markup
from psynet.modular_page import Control, ModularPage, Prompt
from psynet.participant import Participant
from psynet.timeline import NullElt, WebSocketElt


GRID_SIZE = 10
MIN_PLAYERS = 2
MAX_PLAYERS = 10
FORAGING_DURATION = 60
MAX_MOVES = 15  # players buy moves directly, 0-15 per round (Andrade, 29-sep)
MOVE_PRICE = 4  # points per move: 15 moves cost 3 coins (slide 15); not final
VIEW_RADIUS = 1  # fog: each player sees the 3x3 cells around their pac-man
# Fixed coin maps per terrain, made by tools/generate_maps.py (slides 7-8).
MAPS_DIR = Path(__file__).resolve().parent / "static" / "maps"

PLAYER_COLORS = [
    "#f1c40f",
    "#e74c3c",
    "#3498db",
    "#2ecc71",
    "#9b59b6",
    "#e67e22",
    "#1abc9c",
    "#fd79a8",
    "#00cec9",
    "#6c5ce7",
]

SPAWN_POSITIONS = [
    (0, 0),
    (9, 0),
    (0, 9),
    (9, 9),
    (4, 0),
    (5, 9),
    (0, 4),
    (9, 5),
    (4, 4),
    (5, 5),
]

# Round terrains: Andrade's Coordinator_and_Foragers maps scaled to 10x10
# (tools/generate_maps.py): abundant and concentrated first, then scattered and scarce
# (made with Andrade's own generator, tools/generate_scattered_map.py).
ROUND_TERRAINS = ["andrade10_map12", "andrade10_map_scattered"]

# FORAGING_VARIANT=trucks: 3D trucks and spinning coins on Andrade's Coordinator_and_Foragers
# maps (scaled from 80x80 to 20x20), with both trucks leaving from a shared base at the centre.
VARIANT = os.environ.get("FORAGING_VARIANT", "pacman")
if VARIANT == "trucks":
    GRID_SIZE = 20
    MAX_MOVES = 80
    ROUND_TERRAINS = ["andrade_map0", "andrade_map5"]
    SPAWN_POSITIONS = [(9, 10), (10, 10), (9, 9), (10, 9), (8, 10), (11, 10),
                       (8, 9), (11, 9), (9, 11), (10, 11)]


def _patch_dallinger_redis_pubsub_listener():
    """Keep websocket channels alive with redis-py 8.x.

    redis-py 8 defaults socket_timeout to 5s, which makes pubsub.listen()
    raise TimeoutError during idle periods and kills Dallinger's relay greenlets.
    """
    try:
        import redis.exceptions
        from redis import ConnectionError as RedisConnectionError
        from dallinger.experiment_server.sockets import Channel, log, redis_conn
    except ImportError:
        return

    if getattr(Channel, "_redis_timeout_patch", False):
        return

    def listen(self):
        pubsub = redis_conn.pubsub()
        name = self.name
        if isinstance(name, str):
            name = name.encode("utf-8")
        try:
            pubsub.subscribe([name])
        except RedisConnectionError:
            from dallinger.experiment_server.sockets import app

            app.logger.exception("Could not connect to redis.")
        log("Listening on channel {}".format(self.name))
        while True:
            try:
                for message in pubsub.listen():
                    data = message.get("data")
                    if message["type"] == "message" and data != "None":
                        channel = message["channel"]
                        payload = "{}:{}".format(
                            channel.decode("utf-8"), data.decode("utf-8")
                        )
                        for client in self.clients:
                            gevent.spawn(client.send, payload)
                    gevent.sleep(0.001)
            except (TimeoutError, redis.exceptions.TimeoutError):
                gevent.sleep(0.001)

    Channel.listen = listen
    Channel._redis_timeout_patch = True


_patch_dallinger_redis_pubsub_listener()


def last_valid_answer(participant: Participant, label: str):
    """Latest answer to a page that passed validation.

    Answers are written to the trial accumulator before validation, so a rejected
    answer would otherwise shadow the corrected one.
    """
    responses = [
        r
        for r in participant.all_responses
        if r.question == label and r.successful_validation
    ]
    return max(responses, key=lambda r: r.id).answer if responses else None


def active_participant_ids(participant: Participant) -> List[int]:
    return sorted(
        p.id for p in participant.sync_group.participants if not p.failed
    )[:MAX_PLAYERS]


def known_players_for_group(participant: Participant) -> dict:
    """Only seed the local participant; others appear via live websocket state."""
    active_ids = active_participant_ids(participant)
    idx = active_ids.index(participant.id)
    return {
        str(participant.id): {
            "x": SPAWN_POSITIONS[idx][0],
            "y": SPAWN_POSITIONS[idx][1],
            "color": PLAYER_COLORS[idx],
            "coins": 0,
            "collected_coin_coordinates": [],
            "connected": True,
        }
    }


class EnableForaging(NullElt, WebSocketElt):
    """Activates the foraging-game WebSocket channel (same pattern as EnableChatrooms)."""

    channel = "foraging_game"
    _rooms: Dict[str, dict] = {}

    @classmethod
    def mark_disconnected(cls, participant_id, experiment):
        # Keep the player's state: a dropped socket reconnects and rejoins, and the
        # partner should keep seeing the truck (greyed out) in the meantime.
        pid_str = str(participant_id)
        for room_id, room in cls._rooms.items():
            if pid_str not in room["connected"]:
                continue
            room["connected"].discard(pid_str)
            room["players"][pid_str]["connected"] = False
            cls._broadcast_state_for_room(experiment, room_id)

    def handle_message(
        self, message, channel_name, participant, node, receive_time, experiment
    ):
        data = json.loads(message)
        room_id = data.get("room_id")
        if room_id is None:
            return

        msg_type = data.get("type")

        if msg_type in ("join_room", "request_state"):
            if participant is not None:
                room = self._ensure_room(
                    room_id,
                    data.get("grid_size", GRID_SIZE),
                    data.get("terrain", "abundant"),
                )
                self._ensure_round_started(room, receive_time)
                self._register_player(room, participant)
                self._prune_failed_players(room, participant)
                self._broadcast_state(experiment, room_id)

        elif msg_type == "leave_room":
            if participant is not None:
                room = self._rooms.get(room_id)
                if room is not None:
                    self._mark_left(room, participant.id)
                    self._broadcast_state(experiment, room_id)

        elif msg_type == "move":
            if participant is None:
                return
            room = self._rooms.get(room_id)
            if room is None:
                return
            pid_str = str(participant.id)
            if pid_str not in room["connected"]:
                return
            player = room["players"].get(pid_str)
            if player is None:
                return

            dx = int(data.get("dx", 0))
            dy = int(data.get("dy", 0))
            if abs(dx) + abs(dy) != 1 or player["moves_left"] <= 0:
                return

            gs = room["grid_size"]
            x = max(0, min(gs - 1, player["x"] + dx))
            y = max(0, min(gs - 1, player["y"] + dy))
            if (x, y) == (player["x"], player["y"]):
                return  # bumping into the edge costs no move
            player["x"], player["y"] = x, y
            player["moves_left"] -= 1
            player["trajectory"].append([x, y])
            self._collect_coin(room, player)
            self._broadcast_state(experiment, room_id)

    def _ensure_room(
        self, room_id: str, grid_size: int = GRID_SIZE, terrain: str = "abundant"
    ) -> dict:
        if room_id not in self._rooms:
            self._rooms[room_id] = {
                "grid_size": grid_size,
                "terrain": terrain,
                "players": {},
                "connected": set(),
                "coins": self._generate_coins(grid_size, terrain),
                "round_started_at": None,
            }
        return self._rooms[room_id]

    def _ensure_round_started(self, room: dict, receive_time):
        if room["round_started_at"] is not None:
            return
        if receive_time is not None:
            room["round_started_at"] = receive_time.timestamp()
        else:
            room["round_started_at"] = time.time()

    def _generate_coins(self, grid_size: int, terrain: str) -> List[dict]:
        map_file = MAPS_DIR / f"{terrain}.json"
        if map_file.exists():
            positions = [tuple(pos) for pos in json.loads(map_file.read_text())]
        else:
            blocked = set(SPAWN_POSITIONS[:MAX_PLAYERS])
            candidates = [
                (x, y)
                for x in range(grid_size)
                for y in range(grid_size)
                if (x, y) not in blocked
            ]
            positions = random.sample(candidates, min(len(candidates), grid_size + 5))
        return [{"id": i, "x": x, "y": y} for i, (x, y) in enumerate(positions)]

    def _player_state(self, index: int, moves: int) -> dict:
        spawn = SPAWN_POSITIONS[index]
        return {
            "x": spawn[0],
            "y": spawn[1],
            "color": PLAYER_COLORS[index],
            "coins": 0,
            "collected_coin_coordinates": [],
            "moves_bought": moves,
            "moves_left": moves,
            "trajectory": [[spawn[0], spawn[1]]],
            "connected": True,
        }

    def _register_player(self, room: dict, participant: Participant):
        pid_str = str(participant.id)
        room["connected"].add(pid_str)
        if pid_str in room["players"]:
            # Rejoining after a dropped connection: keep position, coins and moves.
            room["players"][pid_str]["connected"] = True
            return
        idx = active_participant_ids(participant).index(participant.id)
        # Moves come from the validated answer in the database, not from the client.
        try:
            moves = round(float(last_valid_answer(participant, "buy_moves") or 0))
        except (TypeError, ValueError):
            moves = 0
        room["players"][pid_str] = self._player_state(idx, min(max(moves, 0), MAX_MOVES))

    def _mark_left(self, room: dict, participant_id: int):
        pid_str = str(participant_id)
        room["connected"].discard(pid_str)
        if pid_str in room["players"]:
            room["players"][pid_str]["connected"] = False

    def _prune_failed_players(self, room: dict, participant: Participant):
        # Only failed participants disappear; disconnected ones stay on the board.
        active_id_strs = {str(pid) for pid in active_participant_ids(participant)}
        for pid_str in list(room["players"]):
            if pid_str not in active_id_strs:
                room["connected"].discard(pid_str)
                room["players"].pop(pid_str, None)

    def _collect_coin(self, room: dict, player: dict):
        for coin in room["coins"]:
            if coin["x"] == player["x"] and coin["y"] == player["y"]:
                room["coins"].remove(coin)
                player["coins"] += 1
                player.setdefault("collected_coin_coordinates", []).append(
                    {"x": coin["x"], "y": coin["y"]}
                )
                break

    def _broadcast_state(self, experiment, room_id: str):
        self._broadcast_state_for_room(experiment, room_id)

    @classmethod
    def _broadcast_state_for_room(cls, experiment, room_id: str):
        room = cls._rooms.get(room_id)
        if room is None:
            return
        payload = {
            "type": "state_update",
            "room_id": room_id,
            "state": {
                "grid_size": room["grid_size"],
                "terrain": room.get("terrain"),
                "players": room["players"],
                "coins": room["coins"],
                "round_started_at": room.get("round_started_at"),
                "timer_duration": FORAGING_DURATION,
            },
        }
        experiment.publish_to_subscribers(
            json.dumps(payload),
            channel_name=cls.channel,
        )


class ForagingPrompt(Prompt):
    macro = "foraging_board"
    external_template = "custom-prompts.html"

    def __init__(
        self,
        room_id: str,
        participant_id: int,
        known_players: dict,
        moves: int,
        terrain: str,
        grid_size: int = GRID_SIZE,
        timer_seconds: int = FORAGING_DURATION,
        title: str = "",
    ):
        super().__init__(text=Markup(title) if title else None)
        self.room_id = room_id
        self.participant_id = participant_id
        self.known_players = known_players
        self.moves = moves
        self.view_radius = VIEW_RADIUS
        self.terrain = terrain
        self.grid_size = grid_size
        self.timer_seconds = timer_seconds
        self.channel = EnableForaging.channel
        self.style = VARIANT


EMPTY_STATS = {
    "coins_collected": 0,
    "moves": 0,
    "collected_coin_coordinates": [],
    "trajectory": [],
}


class ForagingControl(Control):
    macro = "foraging_done"
    external_template = "custom-controls.html"

    def format_answer(self, raw_answer, **kwargs):
        if isinstance(raw_answer, dict):
            return raw_answer
        return dict(EMPTY_STATS)

    def get_bot_response(self, experiment, bot, page, prompt):
        return dict(EMPTY_STATS)


class ForagingPage(ModularPage):
    def __init__(
        self,
        participant: Participant,
        round_id: int,
        moves: int,
        terrain: str,
        title: str = "",
    ):
        # The room ID must be shared by the whole sync group, otherwise each
        # participant would forage alone in their own room. The node ID is shared
        # because followers are assigned the leader's node, while the trial ID is not.
        room_id = f"foraging_{participant.sync_group.id}_{round_id}"
        known_players = known_players_for_group(participant)
        super().__init__(
            label="foraging_page",
            prompt=ForagingPrompt(
                room_id=room_id,
                participant_id=participant.id,
                known_players=known_players,
                moves=moves,
                terrain=terrain,
                grid_size=GRID_SIZE,
                timer_seconds=FORAGING_DURATION,
                title=title,
            ),
            control=ForagingControl(),
            time_estimate=FORAGING_DURATION,
            show_next_button=False,
        )
