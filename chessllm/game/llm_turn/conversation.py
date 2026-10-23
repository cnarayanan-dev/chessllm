"""The Conversation of one LLM side: what its turns send, under its Turn memory. A fresh side's conversation starts
over every turn; under chat_position and chat_moves it lasts the whole game, each turn adding its message.

A conversation keeps every attempt's answer as the LLM sent it and the Retry feedback after it, illegal attempts
included, but never the Thinking. Under Retry feedback repeat a rejected attempt is left out of it, so the next
attempt is sent what the rejected one was. In a conversation each attempt records only the messages it added, and
full_prompt rebuilds the whole Prompt of any attempt from the records (ADR 0009).

A conversation that outgrows the model's context is trimmed by us, never silently by Ollama: before each attempt
the oldest whole earlier turns are dropped, every attempt and its feedback together, until it fits with room left
for the reply. The System prompt and the turn being played always stay.

A question asked at the end of the conversation so far and then dropped from it, as the Legal counterpart is, is
asked aside: it never enters the conversation, nor sizes it."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from chessllm.core.types import Color
from chessllm.game.llm_turn.prompt import fill_system_prompt
from chessllm.game.records import Attempt, LlmTurn, PromptMessage
from chessllm.game.sides import BenchmarkLlmSide, LlmSide, PromptTemplate, TurnMemory
from chessllm.llm.models import BUDGET_SENTENCE, CONTEXT_TOKENS, FORCED_ANSWER_TOKENS
from chessllm.llm.players import Message

# A conservative estimate of the characters per token of a conversation's text: fewer than the models average, so
# the size it gives is never too small. FEN and PGN tokenize densely: llama3:8b counted a chat_position turn's
# message and answer at about 1.6 characters a token, and a chat_moves conversation at about 3, so 3 would be too
# many.
CHARS_PER_TOKEN = 1.5


def reply_reserve(side: LlmSide) -> int:
    """The tokens left in the context for a reply: the side's Thinking budget when it has one, with room for the
    forced answer's call should the budget run out (ADR 0007): its cap, and the sentence handed back with the
    thinking. Otherwise about 4,096 with thinking on and 512 with it off."""
    if isinstance(side, BenchmarkLlmSide) and side.thinking_budget is not None:
        return side.thinking_budget + FORCED_ANSWER_TOKENS + math.ceil(len(BUDGET_SENTENCE) / CHARS_PER_TOKEN)
    return 4096 if side.thinking else 512


@dataclass(frozen=True)
class Aside:
    """A question asked aside from a conversation: the whole Prompt to send, how many earlier turns it holds, and
    whether it fits the context."""

    messages: list[Message]
    remembered: int
    fits: bool


class Conversation:
    """What one LLM side sends to its model, turn after turn, from the Prompt template it plays the game with. The
    System prompt is filled in once, at the side's first turn, and opens every Prompt.

    A turn calls start_turn with its message, then for each attempt messages() (what to send) and record() (what
    its record holds), and once the LLM has answered, answered() with the answer; an answer that isn't played is
    followed by retry() with the Retry feedback, or under Retry feedback repeat by drop_answer()."""

    def __init__(self, turn_memory: TurnMemory, color: Color, template: PromptTemplate) -> None:
        self._turn_memory = turn_memory
        self._color = color
        self._template = template
        self._system: Message | None = None
        self._earlier: list[list[Message]] = []  # each earlier turn the conversation holds, its answers included
        self._turn: list[Message] = []  # this turn's messages so far
        self._added: list[Message] = []  # what the attempt about to be sent adds to the conversation
        # The messages of the last call whose prompt_tokens Ollama reported, each with its share of them.
        self._measured: list[tuple[Message, float]] = []

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
        return self._sent(self._earlier, self._turn)

    def record(self) -> list[PromptMessage]:
        """The next attempt's Prompt as its record has it: the whole Prompt for a fresh turn, and in a conversation
        only the messages it adds (ADR 0009): the System prompt at the side's first attempt, the turn's message at a
        turn's first attempt, then the Retry feedback, and nothing after a dropped answer. Its own answer is the
        attempt's raw_reply."""
        sent = self.messages() if not self.kept else self._added
        return [PromptMessage(role=message.role, content=message.content) for message in sent]

    def answered(self, raw: str) -> None:
        """The attempt's answer, as the LLM sent it, without its Thinking."""
        self._turn.append(Message("assistant", raw))
        self._added = []

    def retry(self, feedback: str) -> None:
        """The Retry feedback after an answer that wasn't played, sent with the next attempt."""
        self._turn.append(Message("user", feedback))
        self._added = [self._turn[-1]]

    def fit(self, reserve: int) -> bool:
        """Drop the oldest whole earlier turns until the conversation to send fits the model's context with reserve
        tokens left for the reply, and say whether it fits: it may not with no earlier turn left to drop, and then
        Ollama may cut it. A fresh Prompt always fits.

        Its size is the last call's prompt_tokens, as Ollama reported them (measured), plus the text added since,
        estimated conservatively at CHARS_PER_TOKEN. A dropped turn takes its share of the tokens with it."""
        if not self.kept:
            return True
        return self._trim(self._earlier, self._turn, reserve)

    def aside(self, question: str, reserve: int) -> Aside:
        """A question asked at the end of a kept conversation so far, its last answer included, which is dropped from
        it once answered: the conversation is left as it is, and the call is never measured into it, so its next
        turn is sent as though the question was never asked. Its Prompt leaves out the oldest whole earlier turns
        until it fits the context with reserve tokens for the reply, as fit does, for itself alone."""
        assert self.kept, "a kept conversation"
        asked = Message("user", question)
        earlier = list(self._earlier)
        fits = self._trim(earlier, [*self._turn, asked], reserve)
        return Aside([*self._sent(earlier, self._turn), asked], len(earlier), fits)

    def _trim(self, earlier: list[list[Message]], last: list[Message], reserve: int) -> bool:
        """Drop the oldest whole turns of earlier, in place, until the System prompt, earlier and last fit the
        context with reserve tokens left for the reply, and say whether they fit."""
        while self._size(self._sent(earlier, last)) + reserve > CONTEXT_TOKENS and earlier:
            del earlier[0]
        return self._size(self._sent(earlier, last)) + reserve <= CONTEXT_TOKENS

    def _sent(self, earlier: list[list[Message]], last: list[Message]) -> list[Message]:
        """The System prompt, then the earlier turns' messages, then last."""
        assert self._system is not None, "a turn has started"
        return [self._system, *(message for turn in earlier for message in turn), *last]

    def measured(self, sent: list[Message], prompt_tokens: int | None) -> None:
        """The prompt_tokens Ollama reported for the messages sent, which size the conversation from then on (fit).
        A message measured by an earlier call keeps its share; those new since share the rest by their characters."""
        if prompt_tokens is None:
            return
        shares = self._shares()
        new = [message for message in sent if id(message) not in shares]
        rest = max(0, prompt_tokens - sum(shares[id(message)] for message in sent if id(message) in shares))
        characters = sum(len(message.content) for message in new) or 1
        for message in new:
            shares[id(message)] = rest * len(message.content) / characters
        self._measured = [(message, shares[id(message)]) for message in sent]

    def _size(self, messages: list[Message]) -> float:
        """The tokens of messages to send: each message's share of a call's prompt_tokens once measured, before that
        its characters at CHARS_PER_TOKEN."""
        shares = self._shares()
        return sum(shares.get(id(message), len(message.content) / CHARS_PER_TOKEN) for message in messages)

    def _shares(self) -> dict[int, float]:
        """Each measured message's share of the last call's prompt_tokens, by the message's identity."""
        return {id(message): tokens for message, tokens in self._measured}

    def drop_answer(self) -> None:
        """Leave the last answer out, under Retry feedback repeat: the next attempt is sent what this one was."""
        assert self._turn[-1].role == "assistant", "an answer to drop"
        self._turn.pop()
        self._added = []


def full_prompt(llm_turns: Sequence[LlmTurn], ply: int, attempt: int) -> list[PromptMessage]:
    """The whole Prompt of an attempt (numbered from 1 in its turn) of the LLM turn at ply, rebuilt from the game's
    LLM turns, as the LLM received it. A fresh turn's attempt has it recorded whole. In a conversation it is the
    side's System prompt, the earlier turns the turn remembered, and this turn's attempts up to this one: what each
    attempt added, and its answer when the conversation kept it (ADR 0009). The earlier turns are the turn's
    remembered, or fewer from a retry that had to drop more of them to fit the context."""
    turn = next(turn for turn in llm_turns if turn.ply == ply)
    if turn.remembered is None:
        return list(turn.attempts[attempt - 1].prompt or [])
    remembered = turn.held(attempt)
    assert remembered is not None, "a turn of a conversation"
    return held(llm_turns, turn, remembered) + kept(turn.attempts[:attempt], ended=False)


def counterpart_prompt(llm_turns: Sequence[LlmTurn], ply: int) -> list[PromptMessage]:
    """The whole Prompt of the Legal counterpart of the chaos move at ply, rebuilt from the game's LLM turns, as the
    LLM received it. A fresh side's has it recorded whole. In a conversation it was asked aside, at the end of the
    conversation so far: the side's System prompt, the earlier turns it held (its attempt's remembered), the chaos
    move's turn to its last answer, then its request, the one message it recorded (ADR 0009)."""
    turn = next(turn for turn in llm_turns if turn.ply == ply)
    assert turn.legal_counterpart is not None, "a chaos move with its Legal counterpart"
    attempt = turn.legal_counterpart.attempt
    if attempt.remembered is None:
        return list(attempt.prompt or [])
    return held(llm_turns, turn, attempt.remembered) + kept(turn.attempts, ended=True) + list(attempt.prompt or [])


def held(llm_turns: Sequence[LlmTurn], turn: LlmTurn, remembered: int) -> list[PromptMessage]:
    """What a conversation sent before a turn of it: the side's System prompt and the last remembered of its
    earlier turns, each as it ended."""
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
