"""Pages that move on by themselves when their time is up.

A player who stops clicking would otherwise sit on a page until the crew barrier that follows
it gives up on them and kicks them (see PARTNER_TIMEOUT_SECONDS in foraging_trucks.py). A
TimedModularPage shows a countdown and, at zero, sends what the page holds, exactly as if the
player had pressed Next. Adapted from custom_front_end.py in nested_ultimatum_group_random_pairing
(without sounds).
"""

import time
from typing import Dict, List, Optional, Union

from markupsafe import Markup
from psynet.modular_page import ModularPage, Prompt


def page_start_persist_key(participant, page_label: str) -> str:
    """Stable across browser refresh; unique per logical page."""
    return f"page_start_{participant.id}_{page_label}"


def persist_page_start_time(
    participant,
    page_label: str,
    fallback: Optional[float] = None,
) -> float:
    """Store the page start time once per page visit; it survives a browser refresh.

    Call it from a CodeBlock just before the page, so that reloading the page does not give
    the player a fresh countdown.
    """
    key = page_start_persist_key(participant, page_label)
    if participant.var.has(key):
        return getattr(participant.var, key)
    start = fallback if fallback is not None else time.time()
    participant.var.set(key, start)
    return start


class TimedModularPage(ModularPage):
    """Binds the TimeoutPrompt start time to participant storage before each render.

    The timer template carries its own style and script tags, so these pages reload fully.
    """

    requires_full_page_reload = True

    def timer_persist_label(self) -> str:
        return f"{self.label}_{self.prompt.round}"

    def render(self, experiment, participant):
        assert isinstance(
            self.prompt, TimeoutPrompt
        ), f"Error: prompt is not a TimeoutPrompt (got {type(self.prompt)})"
        # Rendering runs in a read-only transaction, so this only reads a start time stored
        # earlier by persist_page_start_time. Without one, the browser keeps the same
        # deadline in sessionStorage.
        key = page_start_persist_key(participant, self.timer_persist_label())
        if participant.var.has(key):
            start = getattr(participant.var, key)
        elif self.prompt.currentTime is not None:
            start = self.prompt.currentTime
        else:
            start = time.time()
        self.prompt.currentTime = start
        self.prompt.timerStorageKey = key
        return super().render(experiment, participant)


class TimeoutPrompt(Prompt):
    """A prompt with a countdown.

    submit_current_answer
        True: at zero, the page submits what its control holds (the slider's position), as the
        Next button would. False: it submits timeout_answer instead.
    """

    macro = "timeout"
    external_template = "custom-prompt-with-timer.html"

    def __init__(
        self,
        round_: int,
        timeout: int,
        timeout_answer: Union[str, Dict, None] = "No answer",
        text: Union[None, str, Markup] = None,
        text_align: str = "left",
        buttons: Optional[List] = None,
        loop: bool = False,
        num_rounds: int = 1,
        show_rounds: bool = False,
        submit_current_answer: bool = False,
        current_time: Optional[float] = None,
    ):
        super().__init__(
            text=text,
            text_align=text_align,
            buttons=buttons,
            loop=loop,
        )
        self.timeoutSeconds = timeout
        self.timeoutAnswer = timeout_answer
        self.submitCurrentAnswer = submit_current_answer
        self.currentTime = current_time
        self.timerStorageKey = None
        self.round = round_
        self.num_rounds = num_rounds
        self.show_rounds = show_rounds
