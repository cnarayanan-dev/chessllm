"""The Conversation of one LLM side: what its turns send, under its Turn memory. A fresh side's conversation starts
over every turn; under chat_position it lasts the whole game, each turn adding its message.

A conversation keeps every attempt's answer as the LLM sent it and the Retry feedback after it, illegal attempts
included, but never the Thinking. Under Retry feedback repeat a rejected attempt is left out of it, so the next
attempt is sent what the rejected one was. In a conversation each attempt records only the messages it added, and
full_prompt rebuilds the whole Prompt of any attempt from the records (ADR 0009)."""

from collections.abc import Sequence

from chessllm.core.types import Color
from chessllm.game.llm_turn.prompt import fill_system_prompt
from chessllm.game.records import Attempt, LlmTurn, PromptMessage
from chessllm.game.sides import BenchmarkLlmSide, LlmSide, PromptTemplate, TurnMemory
from chessllm.llm.models import CONTEXT_TOKENS
from chessllm.llm.players import Message

# A conservative estimate of the characters per token of a conversation's text: fewer than the models average, so
# the size it gives is never too small.
CHARS_PER_TOKEN = 3


def reply_reserve(side: LlmSide) -> int:
    """The tokens left in the context for a reply: the side's Thinking budget when it has one, otherwise about 4,096
    with thinking on and 512 with it off."""
    if isinstance(side, BenchmarkLlmSide) and side.thinking_budget is not None:
        return side.thinking_budget
    return 4096 if side.thinking else 512


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

    def answered(self, raw: str) -> None:
        """The attempt's answer, as the LLM sent it, without its Thinking."""
        self._turn.append(Message("assistant", raw))
        self._added = []

    def retry(self, feedback: str) -> None:
        """The Retry feedback after an answer that wasn't played, sent with the next attempt."""
        self._turn.append(Message("user", feedback))
        self._added = [self._turn[-1]]

    def may_not_fit(self, reserve: int) -> bool:
        """Whether the conversation to send may not fit the model's context with reserve tokens left for the reply.
        Until a conversation is trimmed to fit (#106), Ollama would then cut its oldest messages silently, so the
        attempt logs context_may_be_cut. Its size is estimated conservatively, at CHARS_PER_TOKEN; a fresh Prompt
        always fits."""
        size = sum(len(message.content) for message in self.messages()) / CHARS_PER_TOKEN
        return self.kept and size + reserve > CONTEXT_TOKENS

    def drop_answer(self) -> None:
        """Leave the last answer out, under Retry feedback repeat: the next attempt is sent what this one was."""
        assert self._turn[-1].role == "assistant", "an answer to drop"
        self._turn.pop()
        self._added = []


def full_prompt(llm_turns: Sequence[LlmTurn], ply: int, attempt: int) -> list[PromptMessage]:
    """The whole Prompt of an attempt (numbered from 1 in its turn) of the LLM turn at ply, rebuilt from the game's
    LLM turns, as the LLM received it. A fresh turn's attempt has it recorded whole. In a conversation it is the
    side's System prompt, the earlier turns the turn remembered, and this turn's attempts up to this one: what each
    attempt added, and its answer when the conversation kept it (ADR 0009)."""
    turn = next(turn for turn in llm_turns if turn.ply == ply)
    if turn.remembered is None:
        return list(turn.attempts[attempt - 1].prompt or [])
    side = [earlier for earlier in llm_turns if earlier.color == turn.color and earlier.ply <= ply]
    [system, *_] = side[0].attempts[0].prompt or []
    prompt = [system]
    for earlier in side[len(side) - 1 - turn.remembered : -1]:
        prompt += kept(earlier.attempts, ended=True)
    return prompt + kept(turn.attempts[:attempt], ended=False)


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
