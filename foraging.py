import json
import random
import time
from typing import Dict, List

import gevent
from psynet.modular_page import Control, ModularPage, Prompt
from psynet.participant import Participant
from psynet.timeline import NullElt, WebSocketElt


GRID_SIZE = 10
MIN_PLAYERS = 2
MAX_PLAYERS = 10
FORAGING_DURATION = 60

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
        }
    }


class EnableForaging(NullElt, WebSocketElt):
    """Activates the foraging-game WebSocket channel (same pattern as EnableChatrooms)."""

    channel = "foraging_game"
    _rooms: Dict[str, dict] = {}

    @classmethod
    def remove_participant(cls, participant_id, experiment):
        pid_str = str(participant_id)
        for room_id, room in cls._rooms.items():
            if pid_str not in room["connected"]:
                continue
            room["connected"].discard(pid_str)
            room["players"].pop(pid_str, None)
            cls._broadcast_state_for_room(experiment, room_id)

    def handle_message(
        self, message, channel_name, participant, node, receive_time, experiment
    ):
        data = json.loads(message)
        room_id = data.get("room_id")
        if room_id is None:
            return

        msg_type = data.get("type")

        if msg_type == "join_room":
            if participant is not None:
                room = self._ensure_room(room_id, data.get("grid_size", GRID_SIZE))
                self._ensure_round_started(room, receive_time)
                self._register_player(room, participant)
                self._prune_failed_players(room, participant)
                self._broadcast_state(experiment, room_id)

        elif msg_type == "request_state":
            if participant is not None:
                room = self._ensure_room(room_id, data.get("grid_size", GRID_SIZE))
                self._ensure_round_started(room, receive_time)
                self._register_player(room, participant)
                self._prune_failed_players(room, participant)
                self._broadcast_state(experiment, room_id)

        elif msg_type == "leave_room":
            if participant is not None:
                room = self._rooms.get(room_id)
                if room is not None:
                    self._unregister_player(room, participant.id)
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
            if abs(dx) + abs(dy) != 1:
                return

            gs = room["grid_size"]
            player["x"] = max(0, min(gs - 1, player["x"] + dx))
            player["y"] = max(0, min(gs - 1, player["y"] + dy))
            self._collect_coin(room, player)
            self._broadcast_state(experiment, room_id)

    def _ensure_room(self, room_id: str, grid_size: int = GRID_SIZE) -> dict:
        if room_id not in self._rooms:
            self._rooms[room_id] = {
                "grid_size": grid_size,
                "players": {},
                "connected": set(),
                "coins": self._generate_coins(grid_size),
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

    def _generate_coins(self, grid_size: int) -> List[dict]:
        blocked = set(SPAWN_POSITIONS[:MAX_PLAYERS])
        candidates = [
            (x, y)
            for x in range(grid_size)
            for y in range(grid_size)
            if (x, y) not in blocked
        ]
        n_coins = min(len(candidates), grid_size + 5)
        positions = random.sample(candidates, n_coins)
        return [{"id": i, "x": x, "y": y} for i, (x, y) in enumerate(positions)]

    def _player_state(self, index: int) -> dict:
        spawn = SPAWN_POSITIONS[index]
        return {
            "x": spawn[0],
            "y": spawn[1],
            "color": PLAYER_COLORS[index],
            "coins": 0,
            "collected_coin_coordinates": [],
        }

    def _register_player(self, room: dict, participant: Participant):
        pid_str = str(participant.id)
        room["connected"].add(pid_str)
        active_ids = active_participant_ids(participant)
        if pid_str not in room["players"]:
            idx = active_ids.index(participant.id)
            room["players"][pid_str] = self._player_state(idx)

    def _unregister_player(self, room: dict, participant_id: int):
        pid_str = str(participant_id)
        room["connected"].discard(pid_str)
        room["players"].pop(pid_str, None)

    def _prune_failed_players(self, room: dict, participant: Participant):
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
        grid_size: int = GRID_SIZE,
        max_players: int = MAX_PLAYERS,
        timer_seconds: int = FORAGING_DURATION,
        countdown_audio: str = "/static/countdown.mp3",
        coin_collect_audio: str = "/static/coin-collect.mp3",
    ):
        super().__init__()
        self.room_id = room_id
        self.participant_id = participant_id
        self.known_players = known_players
        self.grid_size = grid_size
        self.max_players = max_players
        self.timer_seconds = timer_seconds
        self.countdown_audio = countdown_audio
        self.coin_collect_audio = coin_collect_audio
        self.channel = EnableForaging.channel


class ForagingControl(Control):
    macro = "foraging_done"
    external_template = "custom-controls.html"
    end_when_no_coins = True

    def format_answer(self, raw_answer, **kwargs):
        if isinstance(raw_answer, dict):
            return raw_answer
        return {"coins_collected": 0, "moves": 0, "collected_coin_coordinates": []}

    def get_bot_response(self, experiment, bot, page, prompt):
        return {"coins_collected": 0, "moves": 0, "collected_coin_coordinates": []}


class ForagingPage(ModularPage):
    def __init__(self, participant: Participant, round_id: int):
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
                grid_size=GRID_SIZE,
                max_players=MAX_PLAYERS,
                timer_seconds=FORAGING_DURATION,
            ),
            control=ForagingControl(),
            time_estimate=FORAGING_DURATION,
            show_next_button=False,
        )
