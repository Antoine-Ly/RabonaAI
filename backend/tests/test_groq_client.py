import asyncio
from types import SimpleNamespace

import groq
import httpx
import pytest

from app.core.errors import AppError, ErrorCode
from app.services.llm import groq as groq_module
from app.services.llm.base import Finished, TextDelta, ToolCall, ToolCallsRequested, Usage
from app.services.llm.groq import GroqClient

REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def chunk(content=None, finish=None, usage=None, x_error=None, tool_calls=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choices = [SimpleNamespace(delta=delta, finish_reason=finish)]
    x_groq = SimpleNamespace(usage=usage, error=x_error)
    return SimpleNamespace(choices=choices, usage=None, x_groq=x_groq)


def piece(index=0, call_id=None, name=None, arguments=None):
    function = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(index=index, id=call_id, function=function)


def counts(prompt=100, completion=40):
    return SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)


class FakeStream:
    def __init__(self, chunks, error: Exception | None = None) -> None:
        self.chunks, self.error = chunks, error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def __aiter__(self):
        for c in self.chunks:
            yield c
        if self.error:
            raise self.error


class FakeCompletions:
    def __init__(self, outcomes) -> None:
        self.outcomes, self.calls = list(outcomes), []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_client(outcomes) -> tuple[GroqClient, FakeCompletions]:
    completions = FakeCompletions(outcomes)
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return GroqClient(sdk, "openai/gpt-oss-120b", 1500), completions


def run(client: GroqClient):
    async def go():
        return [e async for e in client.stream("système", [{"role": "user", "content": "Salut"}])]

    return asyncio.run(go())


def status_error(cls, status: int, message: str = "erreur", headers: dict | None = None):
    return cls(
        message, response=httpx.Response(status, headers=headers, request=REQUEST), body=None
    )


GOOD = [chunk("Bon"), chunk("jour"), chunk(finish="stop", usage=counts())]


def test_streams_text_and_usage_from_x_groq() -> None:
    client, _ = make_client([FakeStream(GOOD)])
    assert run(client) == [TextDelta("Bon"), TextDelta("jour"), Finished("stop", Usage(100, 40))]


def test_call_parameters_are_the_v1_ones() -> None:
    client, completions = make_client([FakeStream(GOOD)])
    run(client)
    call = completions.calls[0]
    assert call["model"] == "openai/gpt-oss-120b"
    assert call["temperature"] == 0.2
    assert call["max_completion_tokens"] == 1500
    assert call["stream"] is True
    assert call["messages"] == [
        {"role": "system", "content": "système"},
        {"role": "user", "content": "Salut"},
    ]
    assert "reasoning_effort" not in call and "tools" not in call


def test_per_minute_limit_is_retried_once(monkeypatch: pytest.MonkeyPatch) -> None:
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(groq_module.asyncio, "sleep", fake_sleep)
    limit = status_error(groq.RateLimitError, 429, "tokens per minute (TPM)", {"retry-after": "3"})
    client, completions = make_client([limit, FakeStream(GOOD)])
    assert run(client)[-1] == Finished("stop", Usage(100, 40))
    assert waits == [3.0] and len(completions.calls) == 2


def test_second_per_minute_limit_gives_up() -> None:
    limit = status_error(groq.RateLimitError, 429, "tokens per minute (TPM)", {"retry-after": "0"})
    client, completions = make_client([limit, limit])
    with pytest.raises(AppError) as info:
        run(client)
    assert info.value.code is ErrorCode.LLM_UNAVAILABLE
    assert len(completions.calls) == 2


def test_long_retry_after_is_not_retried() -> None:
    limit = status_error(groq.RateLimitError, 429, "tokens per minute (TPM)", {"retry-after": "30"})
    client, completions = make_client([limit])
    with pytest.raises(AppError) as info:
        run(client)
    assert info.value.code is ErrorCode.LLM_UNAVAILABLE
    assert info.value.retry_after_seconds == 30
    assert len(completions.calls) == 1


def test_daily_limit_is_not_retried() -> None:
    limit = status_error(groq.RateLimitError, 429, "Limit reached on tokens per day (TPD)")
    client, completions = make_client([limit])
    with pytest.raises(AppError) as info:
        run(client)
    assert info.value.code is ErrorCode.QUOTA_GLOBAL_DAILY
    assert len(completions.calls) == 1


def test_limit_after_first_chunk_is_not_retried() -> None:
    limit = status_error(groq.RateLimitError, 429, "tokens per minute (TPM)", {"retry-after": "1"})
    client, completions = make_client([FakeStream([chunk("Bon")], limit)])
    with pytest.raises(AppError) as info:
        run(client)
    assert info.value.code is ErrorCode.LLM_UNAVAILABLE
    assert len(completions.calls) == 1


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (groq.APIConnectionError(request=REQUEST), ErrorCode.LLM_UNAVAILABLE),
        (groq.APITimeoutError(request=REQUEST), ErrorCode.LLM_UNAVAILABLE),
        (status_error(groq.InternalServerError, 503), ErrorCode.LLM_UNAVAILABLE),
        (status_error(groq.AuthenticationError, 401), ErrorCode.INTERNAL_ERROR),
        (status_error(groq.NotFoundError, 404, "model_decommissioned"), ErrorCode.INTERNAL_ERROR),
        (status_error(groq.BadRequestError, 400), ErrorCode.INTERNAL_ERROR),
    ],
)
def test_sdk_errors_are_normalized(error: Exception, code: ErrorCode) -> None:
    client, _ = make_client([error])
    with pytest.raises(AppError) as info:
        run(client)
    assert info.value.code is code
    assert "decommissioned" not in info.value.message  # aucun détail du fournisseur


def test_error_reported_inside_the_stream() -> None:
    client, _ = make_client([FakeStream([chunk("Bon"), chunk(x_error="boom")])])
    with pytest.raises(AppError) as info:
        run(client)
    assert info.value.code is ErrorCode.LLM_UNAVAILABLE


def run_with_tools(client: GroqClient):
    async def go():
        tools = [{"type": "function", "function": {"name": "get_standings"}}]
        return [e async for e in client.stream("système", [], tools)]

    return asyncio.run(go())


def test_tools_are_sent_with_automatic_choice() -> None:
    client, completions = make_client([FakeStream(GOOD)])
    run_with_tools(client)
    call = completions.calls[0]
    assert call["tools"] == [{"type": "function", "function": {"name": "get_standings"}}]
    assert call["tool_choice"] == "auto"


def test_tool_calls_streamed_in_pieces_are_assembled() -> None:
    pieces = [
        chunk(tool_calls=[piece(0, "call_1", "get_standings", '{"compet')]),
        chunk(tool_calls=[piece(0, None, None, 'ition":"ligue-1"}')]),
        chunk(tool_calls=[piece(1, "call_2", "get_top_scorers", "{}")]),
        chunk(finish="tool_calls", usage=counts(300, 20)),
    ]
    client, _ = make_client([FakeStream(pieces)])
    assert run_with_tools(client) == [
        ToolCallsRequested(
            (
                ToolCall("call_1", "get_standings", '{"competition":"ligue-1"}'),
                ToolCall("call_2", "get_top_scorers", "{}"),
            )
        ),
        Finished("tool_calls", Usage(300, 20)),
    ]


def test_tool_call_without_id_gets_a_generated_one() -> None:
    pieces = [chunk(tool_calls=[piece(0, None, "get_standings", "{}")]), chunk(finish="tool_calls")]
    client, _ = make_client([FakeStream(pieces)])
    assert run_with_tools(client)[0].calls[0].id == "call_0"
