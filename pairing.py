"""Random pairing inside a quorum, once per foraging round.

Pairs are reciprocal: each partner's ``PAIR`` var is the other's participant
id. A player left over sits the round out (``PAIR`` is None). The pairing
avoids repeating the previous round's partner when another partner is free,
and a player who just sat out is chosen to play before someone who played.
"""

import random
from typing import Dict, List, Optional, Sequence, Tuple

from dallinger import db
from psynet.participant import Participant
from psynet.sync import SimpleSyncGroup, SyncGroup

from .game_parameters import (
    CONTRACT_BLOCK,
    MIN_GROUP_SIZE,
    N_ROUNDS,
    START_CONTRACT,
)


def proposes_this_round(round_index: int) -> bool:
    """A new contract is proposed after each block of rounds, not after the last."""
    return (int(round_index) + 1) % CONTRACT_BLOCK == 0 and int(round_index) + 1 < N_ROUNDS
from .grouping import GroupRound, Pair, Quorum

CREW_GROUP = "crew"


def match_players(
    participants: Sequence[Participant],
    *,
    sit_out_counts: Optional[Dict] = None,
    previous_sitting_out=(),
) -> Tuple[List[Tuple[Participant, Participant]], List[Participant]]:
    """Pair as many players as possible. An odd player sits the round out.

    Among the players who could sit out, the one who sat out last round is
    kept in the game, then the one who has sat out least often. The matching
    among those who play repeats as few of the immediately previous pairs as
    possible. Every such matching is equally likely.
    """
    players = list(participants)
    if len(players) < 2:
        return [], players
    slots = len(players) - (len(players) % 2)
    counts = sit_out_counts or {}
    playing = _players_for_round(players, slots, counts, previous_sitting_out)
    playing_ids = {person.id for person in playing}
    sitters = [person for person in players if person.id not in playing_ids]
    pairs = _pairing_avoiding_previous(playing)
    return pairs, sitters


def _players_for_round(players, slots, sit_out_counts, previous_sitting_out):
    """Choose who plays, giving the last sitter and least frequent sitters priority."""
    if len(players) <= slots:
        return list(players)
    previous = {int(pid) for pid in previous_sitting_out}
    shuffled = list(players)
    random.shuffle(shuffled)
    shuffled.sort(
        key=lambda person: (
            0 if int(person.id) in previous else 1,
            int(sit_out_counts.get(str(person.id), 0) or 0),
        )
    )
    return shuffled[:slots]


def _repeats(pairs, previous: Dict[int, Optional[int]]) -> int:
    repeats = 0
    for first, second in pairs:
        if (
            previous.get(first.id) == second.id
            or previous.get(second.id) == first.id
        ):
            repeats += 1
    return repeats


def _all_pairings(people):
    """Every way to split ``people`` into unordered pairs. ``people`` has even length."""
    if not people:
        yield []
        return
    first, rest = people[0], people[1:]
    for index, other in enumerate(rest):
        remaining = rest[:index] + rest[index + 1 :]
        for tail in _all_pairings(remaining):
            yield [(first, other)] + tail


def _pairing_avoiding_previous(playing: List[Participant]):
    if len(playing) < 2:
        return []
    previous = {person.id: Pair.previous_partner_id(person) for person in playing}
    population = list(playing)
    random.shuffle(population)
    if len(population) <= 8:
        matchings = list(_all_pairings(population))
    else:
        matchings = []
        for _ in range(200):
            random.shuffle(population)
            matchings.append(_greedy_pairs(list(population), previous))
    best_score = min(_repeats(matching, previous) for matching in matchings)
    best = [
        matching
        for matching in matchings
        if _repeats(matching, previous) == best_score
    ]
    return list(random.choice(best))


def _greedy_pairs(people, previous):
    """One matching. Used when the group is too large to enumerate."""
    remaining = list(people)
    pairs = []
    while len(remaining) >= 2:
        first = remaining.pop(0)
        rest = list(remaining)
        random.shuffle(rest)
        rest.sort(
            key=lambda other: 0
            if previous.get(first.id) != other.id
            and previous.get(other.id) != first.id
            else 1
        )
        other = rest[0]
        remaining.remove(other)
        pairs.append((first, other))
    return pairs


def assign_round_pairs(participant: Participant, round_index: int) -> None:
    """Pair this quorum for ``round_index``, once.

    The first participant to enter the round assigns every eligible member.
    Later arrivals find the round already paired and keep the partner they
    were given. A newcomer whose first eligible round is still ahead sits out.
    """
    quorum = participant.active_sync_groups.get(Quorum.GROUP)
    if quorum is None:
        return
    locked = (
        SyncGroup.query.with_for_update(of=SyncGroup)
        .populate_existing()
        .get(quorum.id)
    )
    if locked is None:
        return
    if int(locked.var.get("paired_round", -1) or -1) == int(round_index):
        # A player who reached this round after the pairs were assigned, including
        # a top-up, sits it out. Everyone already seated keeps their partner.
        in_crew = CREW_GROUP in participant.active_sync_groups
        sitting = bool(participant.var.get("sitting_out", False))
        if not in_crew and not sitting:
            _sit_out(participant)
        return
    if locked.var.get("ended_early"):
        _sit_out(participant)
        return

    members = [
        person
        for person in locked.active_participants
        if person.var.get("out_round", None) is None
        and not person.var.get("left_game", False)
    ]
    eligible = [
        person
        for person in members
        if GroupRound.is_eligible(person, round_index)
    ]
    waiting = [person for person in members if person not in eligible]
    if len(eligible) < MIN_GROUP_SIZE:
        locked.var.set("ended_early", "group_too_small")
        locked.var.set("paired_round", int(round_index))
        for person in members:
            _sit_out(person)
            _leave_crew(person)
        return

    counts = dict(locked.var.get("sit_out_counts") or {})
    previous_sitting = list(locked.var.get("previous_sitting_out") or [])
    pairs, sitters = match_players(
        eligible,
        sit_out_counts=counts,
        previous_sitting_out=previous_sitting,
    )
    for person in list(locked.participants):
        _leave_crew(person)

    if proposes_this_round(round_index):
        # Pairs append their agreements during the round. The next round reads
        # the average stored on the quorum.
        locked.var.set("round_contracts", [])
    contract = locked.var.get("contract", START_CONTRACT)
    for first, second in pairs:
        crew = SimpleSyncGroup(
            group_type=CREW_GROUP,
            initial_group_size=2,
            max_group_size=2,
            min_group_size=1,
            n_active_participants=2,
            accepts_top_ups=False,
            fail_participants_below_min_size=False,
        )
        db.session.add(crew)
        crew.add_participant(first)
        crew.add_participant(second)
        crew.leader = first if first.id < second.id else second
        crew.var.set("contract", contract)
        _seat(first, second.id)
        _seat(second, first.id)
    for person in sitters:
        counts[str(person.id)] = int(counts.get(str(person.id), 0) or 0) + 1
    for person in sitters + waiting:
        _sit_out(person)
    locked.var.set("sit_out_counts", counts)
    locked.var.set("previous_sitting_out", [person.id for person in sitters])
    locked.var.set("paired_round", int(round_index))
    locked.var.set("game_opened", True)
    db.session.flush()


def _seat(participant: Participant, partner_id: int) -> None:
    Pair.assign(participant, partner_id)
    participant.var.set("sitting_out", False)
    # A new partner ends a stretch of playing alone.
    participant.var.set("partner_out_round", None)
    participant.var.set("partner_left", False)


def _sit_out(participant: Participant) -> None:
    Pair.assign(participant, None)
    participant.var.set("sitting_out", True)


def _leave_crew(participant: Participant) -> None:
    crew = participant.active_sync_groups.get(CREW_GROUP)
    if crew is None:
        return
    crew.remove_participant(participant)


def record_pair_contract(participant: Participant, agreed: float) -> None:
    """Fold one pair's agreement into the quorum contract for the following rounds."""
    quorum = participant.active_sync_groups.get(Quorum.GROUP)
    if quorum is None:
        return
    locked = (
        SyncGroup.query.with_for_update(of=SyncGroup)
        .populate_existing()
        .get(quorum.id)
    )
    if locked is None:
        return
    recorded = list(locked.var.get("round_contracts") or [])
    recorded.append(float(agreed))
    locked.var.set("round_contracts", recorded)
    locked.var.set("contract", sum(recorded) / len(recorded))


def finish_round(participant: Participant, round_index: int) -> None:
    """Record who this round was played with, then clear the pair until the next one."""
    partner_id = Pair.current(participant)
    history = list(participant.var.get("round_history") or [])
    history.append({"partner_id": partner_id, "skipped": partner_id is None})
    participant.var.set("round_history", history)
    GroupRound.finish(participant, round_index)
    Pair.assign(participant, None)
    participant.var.set("sitting_out", False)
