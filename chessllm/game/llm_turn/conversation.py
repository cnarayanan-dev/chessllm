"""The Conversation of one LLM side: what its turns send, under its Turn memory. A fresh side's conversation starts
over every turn; under chat_position and chat_moves it lasts the whole game, each turn adding its message, which
under chat_moves the side's Prompt template makes only the opponent's last move.

A conversation keeps every attempt's answer as the LLM sent it and the Retry feedback after it, illegal attempts
included, but never the Thinking. Under Retry feedback repeat a rejected attempt is left out of it, so the next
attempt is sent what the rejected one was. In a conversation each attempt records only the messages it added, and
full_prompt rebuilds the whole Prompt of any attempt from the records (ADR 0009).

A question asked aside, the Legal counterpart of a chaos move, is sent at the end of the conversation and then
dropped from it: the conversation goes on as if it had never been asked. Its record holds only the request, and
counterpart_prompt rebuilds its whole Prompt.

A conversation that would no longer fit the model's context is trimmed by us, never silently by Ollama: before each
attempt the oldest whole earlier turns are dropped until it fits, the System prompt always kept. Should the System
prompt and the turn alone not fit, the attempt logs context_may_be_cut. The Ollama player loads every model with
this context (num_ctx)."""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from chessllm.core.types import Color
from chessllm.game.llm_turn.prompt import fill_system_prompt
from chessllm.game.records import Attempt, LlmTurn, PromptMessage
from chessllm.game.sides import BenchmarkLlmSide, LlmSide, PromptTemplate, TurnMemory
from chessllm.llm.models import BUDGET_SENTENCE, CONTEXT_TOKENS, FORCED_ANSWER_TOKENS
from chessllm.llm.players import Message

# A conservative estimate of the characters per token of a conversation's text: fewer than the models average, so
# the size it gives is never too small.
CHARS_PER_TOKEN = 3


def characters(messages: Iterable[Message]) -> int:
    return sum(len(message.content) for message in messages)


def reply_reserve(side: LlmSide) -> int:
    """The tokens left in the context for a reply: with a Thinking budget, what its forced answer adds to the
    conversation (ADR 0007): the thinking handed back, up to the budget, the sentence closing it and the forced
    answer; otherwise about 4,096 with thinking on and 512 with it off."""
    if isinstance(side, BenchmarkLlmSide) and side.thinking_budget is not None:
        return side.thinking_budget + math.ceil(len(BUDGET_SENTENCE) / CHARS_PER_TOKEN) + FORCED_ANSWER_TOKENS
    return 4096 if side.thinking else 512


@dataclass(frozen=True)
class Aside:
    """A question asked at the end of a conversation and dropped from it: the whole Prompt to send, the request last,
    how many earlier turns it holds, and whether it fits the context."""

    messages: list[Message]
    remembered: int
    fits: bool


class Conversation:
    """What one LLM side sends to its model, turn after turn, from the Prompt template it plays the game with. The
    System prompt is filled in once, at the side's first turn, and opens every Prompt.

    A turn calls start_turn with its message, then for each attempt messages() (what to send) and record() (what
    its record holds), and once the LLM has answered, answered() with the answer; an answer that isn't played is
    followed by retry() with the Retry feedback, or under Retry feedback repeat by drop_answer(). Before each
    attempt fit() trims the conversation to the context."""

    def __init__(self, turn_memory: TurnMemory, color: Color, template: PromptTemplate) -> None:
        self._turn_memory = turn_memory
        self._color = color
        self._template = template
        self._system: Message | None = None
        self._earlier: list[list[Message]] = []  # each earlier turn the conversation holds, its answers included
        self._turn: list[Message] = []  # this turn's messages so far
        self._added: list[Message] = []  # what the attempt about to be sent adds to the conversation
        # The tokens per character of the last call Ollama measured whole, and the messages that call sent.
        self._measured: tuple[float, list[Message]] | None = None
        self._measured_ids: set[int] = set()
        self._fits = True  # whether the conversation fit the context when last trimmed
        self._reserve = 0  # the room for the reply it was last trimmed with

    @property
    def kept(self) -> bool:
        """Whether the conversation outlasts a turn: under every Turn memory but fresh."""
        return self._turn_memory != "fresh"

    @property
    def remembered(self) -> int | None:
        """How many earlier turns this turn's conversation holds; None for a fresh turn, which holds none."""
        return len(self._earlier) if self.kept else None

    def start_turn(self, message: str) -> None:
        """Start a turn with its message, its Turn template filled in: a fresh turn starts a new conversation, a kept
        one adds to it."""
        self._added = []
        if self._system is None:
            self._system = Message("system", fill_system_prompt(self._template.system_prompt, self._color))
            self._added.append(self._system)
        if self.kept and self._turn:
            self._earlier.append(self._turn)
        self._turn = [Message("user", message)]
        self._added.append(self._turn[0])

    def messages(self) -> list[Message]:
        """The whole Prompt to send for the next attempt, as a new list."""
        assert self._system is not None, "a turn has started"
        return [self._system, *(message for turn in self._earlier for message in turn), *self._turn]

    def record(self) -> list[PromptMessage]:
        """The next attempt's Prompt as its record has it: the whole Prompt for a fresh turn, and in a conversation
        only the messages it adds (ADR 0009): the System prompt at the side's first attempt, the turn's message at a
        turn's first attempt, then the Retry feedback, and nothing after a dropped answer. Its own answer is the
        attempt's raw_reply."""
        sent = self.messages() if not self.kept else self._added
        return [PromptMessage(role=message.role, content=message.content) for message in sent]

    def answered(self, raw: str, prompt_tokens: int | None = None) -> None:
        """The attempt's answer, as the LLM sent it, without its Thinking, and the prompt tokens Ollama reported for
        what the attempt sent, if it did."""
        if prompt_tokens is not None:
            # A call that may have reached the context's end may have been cut, and its count with it: trimming
            # then goes back to estimating the whole conversation at CHARS_PER_TOKEN.
            sent = self.messages()
            whole = self._fits and prompt_tokens + self._reserve <= CONTEXT_TOKENS
            self._measured = (prompt_tokens / max(characters(sent), 1), sent) if whole else None
            self._measured_ids = {id(message) for message in sent} if whole else set()
        self._turn.append(Message("assistant", raw))
        self._added = []

    def retry(self, feedback: str) -> None:
        """The Retry feedback after an answer that wasn't played, sent with the next attempt."""
        self._turn.append(Message("user", feedback))
        self._added = [self._turn[-1]]

    def size(self) -> float:
        """The tokens of the conversation to send: the last measured call's prompt tokens, as Ollama reported them,
        plus the text added since at CHARS_PER_TOKEN, a conservative estimate. Messages measured but since dropped
        take their share of the measured tokens with them, by characters. Without a measurement all of it is
        estimated at CHARS_PER_TOKEN."""
        return self._tokens(self.messages())

    def _tokens(self, messages: Sequence[Message]) -> float:
        """The tokens of messages of the conversation: those of the last measured call at its own tokens per
        character, the rest at CHARS_PER_TOKEN."""
        per_character = self._measured[0] if self._measured is not None else 0.0
        return sum(
            len(message.content) * per_character if id(message) in self._measured_ids
            else len(message.content) / CHARS_PER_TOKEN
            for message in messages
        )

    def fit(self, reserve: int) -> bool:
        """Drop the oldest earlier turns, each whole with every attempt and its Retry feedback, until the
        conversation fits the model's context with reserve tokens left for the reply, and say whether it does. The
        System prompt and this turn are never dropped: should they alone not fit, they are sent as they are, and
        the attempt logs that Ollama may cut them (context_may_be_cut)."""
        dropped, size = self._trimmed([], reserve)
        del self._earlier[:dropped]
        self._fits, self._reserve = size + reserve <= CONTEXT_TOKENS, reserve
        return self._fits

    def _trimmed(self, request: Sequence[Message], reserve: int) -> tuple[int, float]:
        """How many of the oldest earlier turns fit drops for the conversation with request after it, and the size
        left."""
        size, dropped = self.size() + self._tokens(request), 0
        while dropped < len(self._earlier) and size + reserve > CONTEXT_TOKENS:
            size -= self._tokens(self._earlier[dropped])
            dropped += 1
        return dropped, size

    def aside(self, request: str, reserve: int) -> Aside:
        """A request asked at the end of the conversation so far, the last answer included, and dropped from it, so
        no later turn is sent it: the conversation is left as it was. Should it not fit the context with reserve
        tokens left for the reply, the oldest earlier turns are dropped for it alone, as fit drops them. Its reply's
        measure is never the conversation's either."""
        assert self.kept and self._system is not None, "a kept conversation that has started"
        asked = Message("user", request)
        dropped, size = self._trimmed([asked], reserve)
        earlier = self._earlier[dropped:]
        messages = [self._system, *(message for turn in earlier for message in turn), *self._turn, asked]
        return Aside(messages, len(earlier), size + reserve <= CONTEXT_TOKENS)

    def drop_answer(self) -> None:
        """Leave the last answer out, under Retry feedback repeat: the next attempt is sent what this one was."""
        assert self._turn[-1].role == "assistant", "an answer to drop"
        self._turn.pop()
        self._added = []


def full_prompt(llm_turns: Sequence[LlmTurn], ply: int, attempt: int) -> list[PromptMessage]:
    """The whole Prompt of an attempt (numbered from 1 in its turn) of the LLM turn at ply, rebuilt from the game's
    LLM turns, as the LLM received it. A fresh turn's attempt has it recorded whole. In a conversation it is the
    side's System prompt, the earlier turns the attempt remembered, and this turn's attempts up to this one: what each
    attempt added, and its answer when the conversation kept it (ADR 0009). An attempt remembered what its turn did,
    unless the conversation was trimmed within the turn: then what the attempt, or the last before it, records."""
    turn = next(turn for turn in llm_turns if turn.ply == ply)
    if turn.remembered is None:
        return list(turn.attempts[attempt - 1].prompt or [])
    remembered = last_remembered(turn.attempts[:attempt], turn.remembered)
    return earlier_turns(llm_turns, turn, remembered) + kept(turn.attempts[:attempt], ended=False)


def counterpart_prompt(llm_turns: Sequence[LlmTurn], ply: int) -> list[PromptMessage]:
    """The whole Prompt of the Legal counterpart of the chaos move of the LLM turn at ply, rebuilt from the game's
    LLM turns, as the LLM received it. A fresh side's has it recorded whole, and so has a conversation's from before
    counterparts were asked inside it, which was sent a fresh Prompt: a recorded Prompt with a System prompt is whole.
    Otherwise it was asked at the end of the conversation as the chaos move's turn left it, and records only its
    request: the side's System prompt, the earlier turns it remembered, the chaos move's turn whole, then the request.
    It remembered what the turn's last attempt did, unless it was trimmed alone: then what it records."""
    turn = next(turn for turn in llm_turns if turn.ply == ply)
    assert turn.legal_counterpart is not None, "a Legal counterpart"
    asked = turn.legal_counterpart.attempt
    recorded = list(asked.prompt or [])
    if turn.remembered is None or any(message.role == "system" for message in recorded):
        return recorded
    remembered = last_remembered([*turn.attempts, asked], turn.remembered)
    return earlier_turns(llm_turns, turn, remembered) + kept(turn.attempts, ended=True) + recorded


def last_remembered(attempts: Sequence[Attempt], remembered: int) -> int:
    """How many earlier turns the last of attempts remembered: its turn's remembered, unless the conversation was
    trimmed within the turn: then what it, or the last before it, records."""
    trimmed = (attempt.remembered for attempt in reversed(attempts) if attempt.remembered is not None)
    return next(trimmed, remembered)


def earlier_turns(llm_turns: Sequence[LlmTurn], turn: LlmTurn, remembered: int) -> list[PromptMessage]:
    """The start of a Prompt of turn in a conversation: the side's System prompt, then the last remembered of its
    earlier turns, each whole."""
    side = [earlier for earlier in llm_turns if earlier.color == turn.color and earlier.ply <= turn.ply]
    [system, *_] = side[0].attempts[0].prompt or []
    prompt = [system]
    for earlier in side[len(side) - 1 - remembered : -1]:
        prompt += kept(earlier.attempts, ended=True)
    return prompt


def kept(attempts: Sequence[Attempt], ended: bool) -> list[PromptMessage]:
    """What a turn's attempts put in the conversation: what each added, and its answer when it was kept: when the
    next attempt answers it with Retry feedback, or, in a turn that has ended, when it was the last."""
    messages: list[PromptMessage] = []
    for number, attempt in enumerate(attempts):
        messages += [message for message in attempt.prompt or [] if message.role != "system"]
        following = attempts[number + 1] if number + 1 < len(attempts) else None
        answer_kept = following.feedback_sent is not None if following is not None else ended
        if answer_kept and attempt.raw_reply is not None:
            messages.append(PromptMessage(role="assistant", content=attempt.raw_reply))
    return messages
