"""Isolated checks for the flexible lobby and for random pairing."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]


def run_lobby_checks():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "dallinger_experiment",
        REPOSITORY / "__init__.py",
        submodule_search_locations=[str(REPOSITORY)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules["dallinger_experiment"] = package
    spec.loader.exec_module(package)

    from dallinger_experiment import grouping
    from dallinger_experiment.game_parameters import (
        BASE_GROUP_SIZE,
        JUMP_START_WAITING_PAGES,
        MIN_GROUP_SIZE,
    )
    from dallinger_experiment.grouping import QuorumGrouper

    class FakeVar(dict):
        def has(self, key):
            return key in self

        def set(self, key, value):
            self[key] = value

    class FakeParticipant:
        def __init__(
            self,
            id_,
            *,
            pages=JUMP_START_WAITING_PAGES,
            last_page_at=1_000.0,
            failed=False,
        ):
            self.id = id_
            self.failed = failed
            self.var = FakeVar(
                unpaired_wait_pages=pages,
                last_lobby_page_at=last_page_at,
            )
            self.active_barriers = {}
            self.sync_group_links = []

    grouper = QuorumGrouper.__new__(QuorumGrouper)
    grouper.initial_group_size = BASE_GROUP_SIZE
    grouper.batch_size = BASE_GROUP_SIZE

    original_time = grouping.time.time
    grouping.time.time = lambda: 1_000.0
    try:
        below_minimum = [
            FakeParticipant(id_) for id_ in range(1, MIN_GROUP_SIZE)
        ]
        assert grouper._short_start_members(below_minimum) == []
        assert not grouper.ready_to_group(below_minimum)

        too_early = [
            FakeParticipant(id_, pages=JUMP_START_WAITING_PAGES - 1)
            for id_ in range(1, MIN_GROUP_SIZE + 1)
        ]
        assert grouper._short_start_members(too_early) == []
        if MIN_GROUP_SIZE < BASE_GROUP_SIZE:
            assert not grouper.ready_to_group(too_early)

        minimum = [
            FakeParticipant(id_) for id_ in range(1, MIN_GROUP_SIZE + 1)
        ]
        short = minimum if MIN_GROUP_SIZE < BASE_GROUP_SIZE else []
        assert grouper._short_start_members(minimum) == short
        assert grouper.ready_to_group(minimum)

        frozen = FakeParticipant(
            MIN_GROUP_SIZE + 1,
            last_page_at=1_000.0 - QuorumGrouper.LOBBY_ACTIVE_SECONDS - 1,
        )
        assert grouper._short_start_members(minimum + [frozen]) == short

        failed = FakeParticipant(MIN_GROUP_SIZE + 2, failed=True)
        assert grouper._short_start_members(minimum + [failed]) == short

        full = [FakeParticipant(id_) for id_ in range(1, BASE_GROUP_SIZE + 1)]
        assert grouper._short_start_members(full) == []
        assert grouper.ready_to_group(full)
    finally:
        grouping.time.time = original_time

    check_top_up_cutoff()
    check_release_before_timeout()
    check_timeout_removal_notice()
    check_pairing()
    check_waiting_counter()


def check_timeout_removal_notice():
    from dallinger_experiment.grouping import QuorumWaitEndLogic
    from psynet.modular_page import ModularPage
    from psynet.timeline import StartSwitch

    sentence = (
        "You have been removed from the experiment because you timed out "
        "too many times."
    )
    page = QuorumWaitEndLogic.timeout_removal_page()
    assert sentence in str(page.prompt.text)
    assert "quorum could not be restored" not in str(page.prompt.text)

    quorum_page = QuorumWaitEndLogic.wait_expired_page()
    assert "quorum could not be restored" in str(quorum_page.prompt.text)
    assert "timed out too many times" not in str(quorum_page.prompt.text)

    class Person:
        def __init__(self, reason, tags=None):
            self.failed_reason = reason
            self.failure_tags = list(tags or [])

    assert QuorumWaitEndLogic.removed_for_timeouts(Person("timeout_rounds"))
    assert QuorumWaitEndLogic.removed_for_timeouts(
        Person("timeout_rounds, UnsuccessfulEndPage")
    )
    assert QuorumWaitEndLogic.removed_for_timeouts(Person("", ["timeout_rounds"]))
    assert not QuorumWaitEndLogic.removed_for_timeouts(Person("unresponsive"))
    assert not QuorumWaitEndLogic.removed_for_timeouts(Person(""))
    assert not QuorumWaitEndLogic.removed_for_timeouts(Person(None))

    logic = QuorumWaitEndLogic().before_debrief_logic()
    notices = [elt for elt in logic if isinstance(elt, StartSwitch)]
    assert [elt.label for elt in notices] == [
        "timeout_rounds_notice",
        "quorum_wait_expired_notice",
    ]
    start = notices[0].branch_start_elts[True]
    pages = [
        elt
        for elt in logic[logic.index(start) :]
        if isinstance(elt, ModularPage)
    ]
    assert sentence in str(pages[0].prompt.text)


def loop_outcome(elts, participant):
    from psynet.timeline import StartSwitch
    from psynet.utils import call_function_with_context

    switches = [elt for elt in elts if isinstance(elt, StartSwitch)]
    for switch in switches:
        taken = call_function_with_context(
            switch.function, participant=participant, experiment=None
        )
        if not taken:
            continue
        if switch.label.endswith("__timed_out") or switch.label == "max_loop_time_condition":
            return "fail"
        return "wait"
    return "exit"


def check_release_before_timeout():
    """A participant released on their last waiting page is not timed out."""
    from dallinger_experiment import grouping
    from dallinger_experiment.game_parameters import BASE_GROUP_SIZE, MAX_WAIT_TIME
    from dallinger_experiment.grouping import ForagingQuorumGrouper, exit_first_while_loop
    from psynet.page import InfoPage
    from psynet.timeline import CodeBlock, StartSwitch
    from psynet.utils import call_function_with_context

    class FakeVar(dict):
        def set(self, key, value):
            self[key] = value

    class Waiter:
        module_state = None

        def __init__(self):
            self.var = FakeVar()
            self.released = False

    elts = exit_first_while_loop(
        "barrier:quorum_grouper",
        lambda participant: not participant.released,
        logic=InfoPage("Waiting", time_estimate=1),
        expected_repetitions=1,
        max_loop_time=MAX_WAIT_TIME,
    )
    start = next(elt for elt in elts if isinstance(elt, CodeBlock))
    original_time = grouping.time.time
    try:
        participant = Waiter()
        grouping.time.time = lambda: 0.0
        start.function(participant)

        grouping.time.time = lambda: MAX_WAIT_TIME - 7.4
        assert loop_outcome(elts, participant) == "wait"

        participant.released = True
        grouping.time.time = lambda: MAX_WAIT_TIME + 25.0
        assert loop_outcome(elts, participant) == "exit"

        participant.released = False
        assert loop_outcome(elts, participant) == "fail"
    finally:
        grouping.time.time = original_time

    barrier = ForagingQuorumGrouper.build(BASE_GROUP_SIZE, "quorum_grouper")
    switches = [elt for elt in barrier.resolve() if isinstance(elt, StartSwitch)]
    labels = [switch.label for switch in switches]
    assert "barrier:quorum_grouper__timed_out" in labels
    assert not any(
        call_function_with_context(
            switch.function, participant=Waiter(), experiment=None
        )
        for switch in switches
        if switch.label == "max_loop_time_condition"
    )


def check_top_up_cutoff():
    """A quorum with too few rounds left takes no top-up."""
    from dallinger_experiment import game_parameters
    from dallinger_experiment.game_parameters import MIN_ROUNDS_LEFT_FOR_TOP_UP, N_ROUNDS
    from dallinger_experiment.grouping import GroupRound, QuorumGrouper

    class FakeVar(dict):
        def has(self, key):
            return key in self

    class Member:
        def __init__(self, round_):
            self.var = FakeVar(group_round=round_, quorum_round_admitted=True)

    class Group:
        def __init__(self, id_, round_):
            self.id = id_
            self.active_participants = [Member(round_) for _ in range(6)]

    def groups_on(*rounds):
        return [Group(id_, round_) for id_, round_ in enumerate(rounds, start=1)]

    for n_rounds in (10, 25, 40):
        last_open = max(
            current
            for current in range(n_rounds + 1)
            if n_rounds - current >= MIN_ROUNDS_LEFT_FOR_TOP_UP * n_rounds
        )
        assert GroupRound.accepts_top_ups(Group(1, last_open), n_rounds)
        assert not GroupRound.accepts_top_ups(Group(1, last_open + 1), n_rounds)
        assert not GroupRound.accepts_top_ups(Group(1, n_rounds), n_rounds)
        assert GroupRound.accepts_top_ups(Group(1, 0), n_rounds)

    assert not GroupRound.accepts_top_ups(Group(1, N_ROUNDS))

    idle = Group(2, 0)
    working = Group(1, 0)
    original_working = GroupRound.is_working
    original_flag = game_parameters.ALLOW_JOIN_WORKING_GROUPS
    try:
        GroupRound.is_working = staticmethod(lambda group: group.id == working.id)
        game_parameters.ALLOW_JOIN_WORKING_GROUPS = False
        assert not GroupRound.accepts_top_ups(working, 10)
        assert GroupRound.accepts_top_ups(idle, 10)
        game_parameters.ALLOW_JOIN_WORKING_GROUPS = True
        assert GroupRound.accepts_top_ups(working, 10)
    finally:
        GroupRound.is_working = original_working
        game_parameters.ALLOW_JOIN_WORKING_GROUPS = original_flag

    class FakeArrival:
        var = FakeVar()

    grouper = QuorumGrouper.__new__(QuorumGrouper)
    cutoff = int(N_ROUNDS - MIN_ROUNDS_LEFT_FOR_TOP_UP * N_ROUNDS) + 1
    candidates = groups_on(cutoff, 0, N_ROUNDS)
    original = QuorumGrouper._available_groups
    try:
        QuorumGrouper._available_groups = lambda self, participant: candidates
        joinable = [group.id for group in grouper._groups_to_join(FakeArrival())]
    finally:
        QuorumGrouper._available_groups = original
    assert joinable == [2]


def check_pairing():
    """Pairs are reciprocal in shape: even players all play, one odd player sits out.

    The previous round's partner is not repeated when another partner is free,
    and the player who just sat out is kept in the game.
    """
    from dallinger_experiment.pairing import match_players

    class Var(dict):
        def has(self, key):
            return key in self

    class Person:
        def __init__(self, id_, history=None):
            self.id = id_
            self.var = Var(round_history=history or [])

    def partner_of(pairs, person):
        for first, second in pairs:
            if first.id == person.id:
                return second.id
            if second.id == person.id:
                return first.id
        return None

    people = [Person(i) for i in range(1, 4)]
    for _ in range(20):
        pairs, sitters = match_players(people)
        assert len(pairs) == 1
        assert len(sitters) == 1
        seated = {people[0].id, people[1].id, people[2].id}
        used = {pairs[0][0].id, pairs[0][1].id, sitters[0].id}
        assert used == seated

    previous_sitter = Person(1)
    others = [Person(2), Person(3)]
    for _ in range(30):
        pairs, sitters = match_players(
            [previous_sitter, *others],
            previous_sitting_out=[previous_sitter.id],
        )
        assert partner_of(pairs, previous_sitter) is not None
        assert sitters[0].id != previous_sitter.id

    played = [
        Person(1, [{"partner_id": 2, "skipped": False}]),
        Person(2, [{"partner_id": 1, "skipped": False}]),
        Person(3, [{"partner_id": 4, "skipped": False}]),
        Person(4, [{"partner_id": 3, "skipped": False}]),
    ]
    for _ in range(40):
        pairs, sitters = match_players(played)
        assert sitters == []
        assert partner_of(pairs, played[0]) != 2
        assert partner_of(pairs, played[2]) != 4

    alone = [Person(1)]
    pairs, sitters = match_players(alone)
    assert pairs == []
    assert sitters == alone


def check_waiting_counter():
    """Drawing a lobby page raises the unpaired count and refreshes the timestamp."""
    from dallinger_experiment import waiting

    class Var(dict):
        def has(self, key):
            return key in self

        def set(self, key, value):
            self[key] = value

    class Trial:
        id = 7

    class Person:
        def __init__(self):
            self.var = Var()
            self.current_trial = Trial()

    person = Person()
    waiting.time.time = lambda: 50.0
    assert waiting.consecutive_unpaired_waits(person) == 1
    assert person.var["unpaired_wait_pages"] == 1
    assert person.var["last_lobby_page_at"] == 50.0
    # The same trial drawn again does not count twice.
    assert waiting.consecutive_unpaired_waits(person) == 1
    person.current_trial = Trial()
    person.current_trial.id = 8
    waiting.time.time = lambda: 60.0
    assert waiting.consecutive_unpaired_waits(person) == 2
    assert person.var["last_lobby_page_at"] == 60.0


def test_flexible_lobby_logic_in_isolated_process():
    subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--run-regression"],
        cwd=REPOSITORY,
        check=True,
    )


if __name__ == "__main__" and "--run-regression" in sys.argv:
    run_lobby_checks()
    print("flexible lobby checks passed")
