import time
from typing import List, Optional

from markupsafe import Markup
from psynet.end import SuccessfulEndLogic, UnsuccessfulEndLogic
from psynet.modular_page import ModularPage
from psynet.page import UnsuccessfulEndPage
from psynet.participant import Participant
from psynet.timeline import CodeBlock, Event, conditional, join, while_loop
from psynet.sync import (
    Barrier,
    ParticipantLinkBarrier,
    SimpleGrouper,
    SimpleSyncGroup,
    SyncGroup,
)

from .game_parameters import (
    BASE_GROUP_SIZE,
    END_PAGE_SECONDS,
    INTRO_PAGE_TIME_ESTIMATE,
    JUMP_START_WAITING_PAGES,
    MIN_GROUP_SIZE,
    MIN_ROUNDS_LEFT_FOR_TOP_UP,
    N_ROUNDS,
    UNRESPONSIVE_WAITING_PAGES,
    WAITING_TRIAL_TIME_ESTIMATE,
)


class Quorum:
    """The base group participants must fill before they can be paired."""

    GROUP = "quorum"
    BARRIER_ID = "quorum_grouper"
    DEBUG_BARRIER_ID = "debug_quorum_grouper"

    @staticmethod
    def for_participant(participant: Participant):
        """The quorum this person belongs to, including one that has closed.

        The score table is shown after the game closes the group. An active
        group is used when there is one. Otherwise the last membership is used.
        """
        active = participant.active_sync_groups.get(Quorum.GROUP)
        if active is not None:
            return active
        matches = [
            link.sync_group
            for link in getattr(participant, "sync_group_links", []) or []
            if getattr(link, "active", True)
            and getattr(getattr(link, "sync_group", None), "group_type", None)
            == Quorum.GROUP
        ]
        return matches[-1] if matches else None

    @staticmethod
    def sort_by_arrival(participant_ids):
        """Order ids by when they reached the quorum grouper, earliest first."""
        if not participant_ids:
            return []
        links = ParticipantLinkBarrier.query.filter(
            ParticipantLinkBarrier.barrier_id.in_(
                [Quorum.BARRIER_ID, Quorum.DEBUG_BARRIER_ID]
            ),
            ParticipantLinkBarrier.participant_id.in_(list(participant_ids)),
        ).all()
        first_arrival = {}
        for link in links:
            arrived = link.arrival_time
            previous = first_arrival.get(link.participant_id)
            if arrived is not None and (previous is None or arrived < previous):
                first_arrival[link.participant_id] = arrived

        def key(pid):
            arrived = first_arrival.get(pid)
            # Missing arrivals sort last. timestamp() avoids mixing naive and aware datetimes.
            if arrived is None:
                return (1, 0.0, pid)
            return (0, arrived.timestamp(), pid)

        return sorted(participant_ids, key=key)

    @staticmethod
    def roster():
        """
        Who is waiting to form a quorum, and who is already in one.

        ``waiting`` is everyone still held at the quorum grouper, in arrival order.
        ``groups`` maps each active quorum group to its members, also in arrival
        order. The client shows the batch of ``BASE_GROUP_SIZE`` that contains
        the viewer.
        """
        links = (
            ParticipantLinkBarrier.query.join(Participant)
            .filter(
                ParticipantLinkBarrier.barrier_id.in_(
                    [Quorum.BARRIER_ID, Quorum.DEBUG_BARRIER_ID]
                ),
                ~ParticipantLinkBarrier.released,
                ~Participant.failed,
                Participant.status == "working",
            )
            .order_by(ParticipantLinkBarrier.arrival_time, Participant.id)
            .all()
        )
        waiting = []
        for link in links:
            if link.participant_id not in waiting:
                waiting.append(link.participant_id)

        groups = {}
        active_groups = SimpleSyncGroup.query.filter_by(
            group_type=Quorum.GROUP, active=True
        ).all()
        for group in active_groups:
            member_ids = [p.id for p in group.active_participants]
            groups[str(group.id)] = Quorum.sort_by_arrival(member_ids)
        return {"waiting": waiting, "groups": groups, "avatars": {}}

    @staticmethod
    def is_full(participant: Participant) -> bool:
        """True when the quorum still has at least its minimum number of players.

        The lobby forms at the initial size. After that, a group at or above
        ``min_group_size`` keeps playing and does not wait to refill. A missing
        group is not quorate. The stored member count can lag behind the live
        members, so this counts the live list.
        """
        quorum = participant.active_sync_groups.get(Quorum.GROUP)
        if quorum is None or not quorum.min_group_size:
            return False
        return len(quorum.active_participants) >= quorum.min_group_size

    @staticmethod
    def mark_wait_expired(participant: Participant):
        """Remember that the quorum could not be restored in time."""
        participant.var.set("quorum_wait_expired", True)

    @staticmethod
    def wait_expired(participant: Participant) -> bool:
        return bool(participant.var.get("quorum_wait_expired", False))


class Pair:
    """Who this participant is paired with for the current round.

    ``PAIR`` stores the partner's participant id. It is ``None`` while the
    participant is sitting out or waiting between rounds. The table they play
    at is a separate session id.
    """

    @staticmethod
    def current(participant: Participant) -> Optional[int]:
        """Partner participant id for this round, or None when unpaired."""
        if not participant.var.has("PAIR"):
            return None
        value = participant.var.get("PAIR")
        if value is None:
            return None
        try:
            partner_id = int(value)
        except (TypeError, ValueError):
            return None
        if partner_id <= 0:
            return None
        return partner_id

    @staticmethod
    def assign(participant: Participant, partner_id: Optional[int]):
        """Record this round's partner. None means sitting out or between rounds."""
        if partner_id is None:
            participant.var.set("PAIR", None)
            return
        participant.var.set("PAIR", int(partner_id))

    @staticmethod
    def previous_partner_id(participant: Participant) -> Optional[int]:
        """Partner from the latest round this participant actually played."""
        history = participant.var.get("round_history", []) or []
        for item in reversed(history):
            if not isinstance(item, dict) or item.get("skipped"):
                continue
            partner_id = item.get("partner_id")
            if partner_id is not None:
                return int(partner_id)
        return None


class GroupRound:
    """Which round a quorum is on, shared by its members through their vars."""

    ELIGIBLE_ROUND_VAR = "quorum_eligible_round"
    ADMITTED_VAR = "quorum_round_admitted"

    @staticmethod
    def done_key(round_index) -> str:
        return f"quorate_round_{round_index}_done"

    @staticmethod
    def is_done(participant: Participant, round_index) -> bool:
        return bool(participant.var.get(GroupRound.done_key(round_index), False))

    @staticmethod
    def current(participant: Participant) -> int:
        """Round index the quorum is on. A replacement reads this and skips ahead."""
        quorum = participant.active_sync_groups.get(Quorum.GROUP)
        members = (
            list(quorum.active_participants) if quorum is not None else [participant]
        )
        return GroupRound.current_of(members)

    @staticmethod
    def current_of(members: List[Participant]) -> int:
        """Round index a group with these members is on."""
        admitted = [
            member
            for member in members
            if bool(member.var.get(GroupRound.ADMITTED_VAR, False))
        ]
        # A queued top-up may already be waiting at the next round. It must not
        # make incumbents look stale while they finish the current round.
        if admitted:
            members = admitted
        rounds = [
            int(member.var.get("group_round") or 0)
            for member in members
            if member.var.has("group_round")
        ]
        return max(rounds) if rounds else 0

    @staticmethod
    def is_working(group) -> bool:
        """Whether this quorum has opened the game.

        A quorum still in the lobby has not. Once a round has been paired,
        ``game_opened`` is set and late arrivals follow the top-up rules.
        """
        if not isinstance(group, SimpleSyncGroup):
            return False
        return bool(group.var.get("game_opened", False))

    @staticmethod
    def accepts_top_ups(group, n_rounds: int = N_ROUNDS) -> bool:
        """Whether a newcomer may join ``group``.

        A quorum still filling in the lobby can grow. Once it has opened the
        game, newcomers join only when ``ALLOW_JOIN_WORKING_GROUPS`` is on and
        enough rounds remain.
        """
        from . import game_parameters

        if not game_parameters.ALLOW_JOIN_WORKING_GROUPS and GroupRound.is_working(group):
            return False
        left = n_rounds - GroupRound.current_of(list(group.active_participants))
        return left >= MIN_ROUNDS_LEFT_FOR_TOP_UP * n_rounds

    @staticmethod
    def participant_round(participant: Participant) -> int:
        return int(participant.var.get("group_round", 0) or 0)

    @staticmethod
    def eligible_round(participant: Participant) -> int:
        """First round in which this quorum member may be paired."""
        return int(
            participant.var.get(GroupRound.ELIGIBLE_ROUND_VAR, 0) or 0
        )

    @staticmethod
    def is_eligible(participant: Participant, round_index: int) -> bool:
        return GroupRound.eligible_round(participant) <= int(round_index)

    @staticmethod
    def pairing_started(participant: Participant, round_index: int) -> bool:
        """Whether this round's pairs are already open.

        A player who arrives after that waits for the following round.
        """
        quorum = participant.active_sync_groups.get(Quorum.GROUP)
        if quorum is None:
            return False
        # Set when this round's pairs are assigned, cleared conceptually by
        # moving paired_round on to the next round. A late arrival waits.
        return int(quorum.var.get("paired_round", -1) or -1) == int(round_index)

    @staticmethod
    def first_eligible_round(participant: Participant) -> int:
        """Queue a top-up for the next round if pairing has already started."""
        current = GroupRound.current(participant)
        if GroupRound.pairing_started(participant, current):
            return current + 1
        return current

    @staticmethod
    def catch_up_target(participant: Participant) -> int:
        """First round this participant should enter in the timeline."""
        return max(
            GroupRound.current(participant),
            GroupRound.eligible_round(participant),
        )

    @staticmethod
    def has_advanced_past(participant: Participant, round_index: int) -> bool:
        return GroupRound.participant_round(participant) > int(round_index)

    @staticmethod
    def note(participant: Participant, round_index):
        current = -1
        if participant.var.has("group_round"):
            current = int(participant.var.get("group_round") or -1)
        if round_index > current:
            participant.var.set("group_round", int(round_index))

    @staticmethod
    def finish(participant: Participant, round_index):
        participant.var.set(GroupRound.done_key(round_index), True)
        # Later arrivals should join the next round, not replay this one.
        participant.var.set("group_round", int(round_index) + 1)
        if GroupRound.is_eligible(participant, round_index):
            participant.var.set(GroupRound.ADMITTED_VAR, True)

    @staticmethod
    def others_still_paired(participant: Participant, round_index) -> bool:
        """True while someone else is still inside this round's pair.

        A player who is sitting this round out has no pair. They stay on the
        lobby until those pairs close.
        """
        quorum = participant.active_sync_groups.get(Quorum.GROUP)
        if quorum is None:
            return False
        for member in quorum.active_participants:
            if member.id == participant.id or GroupRound.is_done(member, round_index):
                continue
            if Pair.current(member) is not None:
                return True
        return False


class KickedOut:
    """Participants removed for not responding."""

    @staticmethod
    def mark(participant: Participant):
        """Remember that this participant was removed for not responding."""
        participant.var.set("kicked_out", True)


def exit_first_while_loop(
    label,
    keep_waiting,
    logic,
    expected_repetitions,
    max_loop_time,
    *,
    fix_time_credit=True,
    on_timeout=None,
    fail_on_timeout=True,
):
    """Loop ``logic`` while ``keep_waiting(participant)``, for at most ``max_loop_time`` s.

    PsyNet's ``while_loop`` checks its time limit before its condition, so a
    participant whose wait ended while they were on a waiting page still timed
    out when that page ended. Here the condition is checked first: only
    someone who is still waiting when the time is up times out.
    """
    started_key = f"__{label}__exit_first_started_at"

    def timed_out(participant):
        return time.time() - float(participant.var.get(started_key)) >= max_loop_time

    after_timeout = [CodeBlock(on_timeout)] if on_timeout is not None else []
    if fail_on_timeout:
        after_timeout.append(
            UnsuccessfulEndPage(failure_tags=[f"while_loop:{label}", "fail_on_timeout"])
        )
    return join(
        CodeBlock(lambda participant: participant.var.set(started_key, time.time())),
        while_loop(
            label,
            lambda participant: keep_waiting(participant) and not timed_out(participant),
            logic=logic,
            expected_repetitions=expected_repetitions,
            fix_time_credit=fix_time_credit,
        ),
        conditional(
            f"{label}__timed_out",
            keep_waiting,
            logic_if_true=join(*after_timeout) if after_timeout else CodeBlock(lambda: None),
            time_estimate=0.0,
            log_chosen_branch=False,
        ),
    )


class _ReleaseBeforeTimeout(Barrier):
    """A barrier with waiting pages that lets a released participant through.

    The release is checked before ``max_wait_time``, so someone released while
    on their last waiting page continues instead of timing out. Barriers on
    PsyNet's default hold page already behave this way.
    """

    def resolve(self):
        # This PsyNet checks a barrier's time limit before its release condition,
        # so someone released on their last waiting page would still time out.
        # Always check the release first.
        elts = join(
            CodeBlock(lambda participant: self.receive_participant(participant)),
            exit_first_while_loop(
                f"barrier:{self.id}",
                lambda participant: not self.can_participant_exit(participant),
                logic=self.waiting_logic,
                expected_repetitions=self.waiting_logic_expected_repetitions,
                max_loop_time=self.max_wait_time,
                fix_time_credit=self.fix_time_credit,
                on_timeout=self.handle_max_wait_timeout,
                fail_on_timeout=self.max_wait_action == "fail",
            ),
            conditional(
                "participant_failed",
                condition=lambda participant: participant.failed,
                logic_if_true=UnsuccessfulEndPage(),
                time_estimate=0,
                log_chosen_branch=False,
            ),
        )
        for elt in elts:
            elt.links["barrier"] = self
        return elts



class QuorumGrouper(SimpleGrouper, _ReleaseBeforeTimeout):
    """Form a quorum, and let a subclass give each member a role.

    The main lobby also starts below ``BASE_GROUP_SIZE``: once
    ``MIN_GROUP_SIZE`` or more active people are waiting and the longest
    waiter has seen ``JUMP_START_WAITING_PAGES`` lobby pages, those people
    form the quorum. Later arrivals can still top it up.
    """

    # A lobby member counts toward a short start only if they loaded a new
    # lobby page this recently. Background tabs stop advancing the lobby.
    LOBBY_ACTIVE_SECONDS = UNRESPONSIVE_WAITING_PAGES * WAITING_TRIAL_TIME_ESTIMATE

    @staticmethod
    def lobby_is_active(participant: Participant) -> bool:
        last_page = participant.var.get("last_lobby_page_at", None)
        if last_page is None:
            return False
        return time.time() - float(last_page) <= QuorumGrouper.LOBBY_ACTIVE_SECONDS

    def assign_arrival_role(self, participant: Participant) -> None:
        """Give a role to a participant who has just reached the grouper."""

    def assign_group_roles(self, members: List[Participant]) -> None:
        """Give roles to the members of a quorum that has just formed or grown."""

    def receive_participant(self, participant: Participant):
        super().receive_participant(participant)
        self.assign_arrival_role(participant)

    def _short_start_members(self, participants: List[Participant]) -> List[Participant]:
        if int(self.initial_group_size) != BASE_GROUP_SIZE:
            return []
        active = [
            person
            for person in participants
            if not person.failed and QuorumGrouper.lobby_is_active(person)
        ]
        if not MIN_GROUP_SIZE <= len(active) < BASE_GROUP_SIZE:
            return []
        pages = max(int(person.var.get("unpaired_wait_pages", 0) or 0) for person in active)
        if pages < JUMP_START_WAITING_PAGES:
            return []
        return active

    def ready_to_group(self, participants: List[Participant]) -> bool:
        return super().ready_to_group(participants) or bool(
            self._short_start_members(participants)
        )

    def _available_groups(self, participant: Participant):
        """Quorums with room, smallest first. This PsyNet has no ``_groups_to_join``."""
        if not self.join_existing_groups:
            return []
        query = SimpleSyncGroup.query.filter(
            SimpleSyncGroup.group_type == self.group_type,
            SimpleSyncGroup.active.is_(True),
        )
        if self.max_group_size is not None:
            query = query.filter(
                SimpleSyncGroup.n_active_participants < self.max_group_size
            )
        return query.order_by(
            SimpleSyncGroup.n_active_participants, SimpleSyncGroup.id
        ).all()

    def _groups_to_join(self, participant: Participant):
        # A lobby tab that stopped advancing would only hold up the quorum it
        # joins. A new arrival has no lobby page yet and may join.
        if participant.var.get("last_lobby_page_at", None) is not None and not (
            QuorumGrouper.lobby_is_active(participant)
        ):
            return
        criterion = getattr(self, "join_criterion", None)
        for group in self._available_groups(participant):
            if criterion is not None and not criterion(
                group=group, participant=participant
            ):
                continue
            if GroupRound.accepts_top_ups(group):
                yield group

    def group(self, participants: List[Participant]) -> List[SyncGroup]:
        if super().ready_to_group(participants):
            groups = super().group(participants)
        else:
            members = self._short_start_members(participants)
            groups = [self._short_group(members)] if members else []
        for group in groups:
            members = list(group.participants)
            self.assign_group_roles(members)
            for person in members:
                person.var.set("quorum_start_size", len(members))
                person.var.set(GroupRound.ELIGIBLE_ROUND_VAR, 0)
                person.var.set(GroupRound.ADMITTED_VAR, True)
        return groups

    def _short_group(self, members: List[Participant]) -> SimpleSyncGroup:
        group = SimpleSyncGroup(
            group_type=self.group_type,
            initial_group_size=len(members),
            max_group_size=self.max_group_size,
            min_group_size=self.min_group_size,
            n_active_participants=len(members),
            accepts_top_ups=self.join_existing_groups,
            fail_participants_below_min_size=self.fail_participants_below_min_size,
        )
        for person in members:
            group.add_participant(person)
        group.leader = self.select_leader(members)
        return group

    def _join_existing_groups(self, participant: Participant):
        groups = list(self._groups_to_join(participant))
        if not groups:
            return
        group = groups[0]
        group.add_participant(participant)
        group.check_numbers()
        group.check_leader()
        participant.var.set(GroupRound.ADMITTED_VAR, False)
        participant.var.set(
            GroupRound.ELIGIBLE_ROUND_VAR,
            GroupRound.first_eligible_round(participant),
        )
        self.assign_group_roles(list(group.participants))

    def handle_max_wait_timeout(self, participant: Participant):
        Quorum.mark_wait_expired(participant)
        super().handle_max_wait_timeout(participant)


class _AutoContinueEnd:
    """Replace the Finish button with the same countdown as a timeout notice."""

    def _finish_next_step(self, experiment):
        return "This page continues on its own."

    def debrief_page(self, content, experiment, participant, show_finish_button=True):
        if not show_finish_button:
            return super().debrief_page(
                content,
                experiment,
                participant,
                show_finish_button=False,
            )
        body = Markup(
            f"{content}"
            "<p class='failed-page-countdown'>"
            "Continuing automatically in "
            f"<span id='end-page-timer'>{END_PAGE_SECONDS}</span> seconds."
            "</p>"
        )
        return ModularPage(
            self.__class__.__name__,
            body,
            control=None,
            show_next_button=False,
            time_estimate=END_PAGE_SECONDS,
            bot_response="No answer",
            css="""
                .failed-page-countdown {
                    margin-top: 1.5rem;
                    font-size: 1.1rem;
                    color: #334155;
                }
                """,
            events={
                "autoSubmit": Event(
                    is_triggered_by="trialStart",
                    delay=float(END_PAGE_SECONDS),
                    once=True,
                    js="psynet.submitResponse()",
                ),
            },
        )


class CompletedEndLogic(_AutoContinueEnd, SuccessfulEndLogic):
    """Successful end screen that continues without a Finish click."""


class QuorumWaitEndLogic(_AutoContinueEnd, UnsuccessfulEndLogic):
    """Explain why this participant stopped, then show the early-end page."""

    # Same pause as the personality timeout page before the early-end page.
    NOTICE_SECONDS = 4

    @staticmethod
    def removed_for_timeouts(participant: Participant) -> bool:
        """Whether this participant was removed for timing out too often."""
        reason = getattr(participant, "failed_reason", None) or ""
        tags = list(getattr(participant, "failure_tags", None) or [])
        parts = [part.strip() for part in str(reason).split(",")]
        return "timeout_rounds" in parts or "timeout_rounds" in tags

    @staticmethod
    def _reason_page(label: str, explanation: str):
        """A short reason screen that continues to the early-end page."""
        seconds = QuorumWaitEndLogic.NOTICE_SECONDS
        return ModularPage(
            label=label,
            prompt=Markup(
                "<h3>End of experiment</h3>"
                f"<p>{explanation}</p>"
                "<br>"
                "<p>Thank you for your participation. Please follow the instructions "
                "to return to the recruiter and receive your payment.</p>"
                "<p class='failed-page-countdown'>"
                "Continuing automatically in "
                f"<span id='failed-page-timer'>{seconds}</span> seconds."
                "</p>"
            ),
            control=None,
            show_next_button=False,
            time_estimate=INTRO_PAGE_TIME_ESTIMATE,
            save_answer=label,
            css="""
                .failed-page-countdown {
                    margin-top: 1.5rem;
                    font-size: 1.1rem;
                    color: #334155;
                }
                """,
            events={
                "autoSubmit": Event(
                    is_triggered_by="trialStart",
                    delay=float(seconds),
                    once=True,
                    js="psynet.submitResponse()",
                ),
            },
        )

    @staticmethod
    def wait_expired_page():
        """Explain a broken quorum, then continue to the early-end page."""
        return QuorumWaitEndLogic._reason_page(
            "quorum_wait_expired_reason",
            "The experiment finished for the following reason: "
            "Unfortunately, one or more participants left the group and the "
            "quorum could not be restored in the allotted time.",
        )

    @staticmethod
    def timeout_removal_page():
        """Tell a player they were removed for timing out too often."""
        return QuorumWaitEndLogic._reason_page(
            "timeout_rounds_reason",
            "You have been removed from the experiment because you timed out "
            "too many times.",
        )

    def before_debrief_logic(self):
        return join(
            conditional(
                "timeout_rounds_notice",
                QuorumWaitEndLogic.removed_for_timeouts,
                QuorumWaitEndLogic.timeout_removal_page(),
                log_chosen_branch=False,
            ),
            conditional(
                "quorum_wait_expired_notice",
                Quorum.wait_expired,
                QuorumWaitEndLogic.wait_expired_page(),
                log_chosen_branch=False,
            ),
        )


class ForagingQuorumGrouper(QuorumGrouper):
    """Lobby barrier. Foraging has no roles, so arrival and group hooks stay empty."""

    @staticmethod
    def build(group_size, barrier_id, *, min_group_size=None):
        """Form a quorum of ``group_size`` that can later play with fewer people.

        The lobby waits until ``group_size`` people are present. It can start
        earlier, down to ``MIN_GROUP_SIZE`` active people, once one of them has
        seen ``JUMP_START_WAITING_PAGES`` lobby pages. Later arrivals can still
        join a game in progress when ``ALLOW_JOIN_WORKING_GROUPS`` is on and
        enough rounds remain.
        """
        from .game_parameters import MAX_WAIT_TIME
        from .waiting import lobby_waiting_logic

        # The sync group's own minimum is 1. Pairing ends the game when fewer
        # than MIN_GROUP_SIZE can play, and those players still have to pass
        # the quorum's barriers to reach the results page. A PsyNet minimum of
        # MIN_GROUP_SIZE would hold the last player at the barrier instead.
        if min_group_size is None:
            min_group_size = 1
        return ForagingQuorumGrouper(
            Quorum.GROUP,
            id_=barrier_id,
            initial_group_size=group_size,
            max_group_size=group_size,
            min_group_size=min_group_size,
            join_existing_groups=True,
            fail_participants_below_min_size=False,
            waiting_logic=lobby_waiting_logic(),
            waiting_logic_expected_repetitions=10,
            max_wait_time=MAX_WAIT_TIME,
        )


