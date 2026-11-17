import asyncio
from datetime import UTC, datetime

from app.core.errors import AppError, ErrorCode
from app.services.chat import build_system_prompt, load_prompt, stream_chat
from app.services.llm.base import Finished, TextDelta, Usage


class FakeLLM:
    """Client LLM scripté : aucun réseau."""

    def __init__(self, events=(), error: Exception | None = None) -> None:
        self.events = list(events)
        self.error = error
        self.calls: list[tuple[str, list[dict[str, str]]]] = []

    async def stream(self, system, messages):
        self.calls.append((system, messages))
        for event in self.events:
            yield event
        if self.error:
            raise self.error


def collect(llm, message="Salut", now=None):
    async def run():
        return [item async for item in stream_chat(llm, message, now)]

    return asyncio.run(run())


def test_relays_deltas_then_done() -> None:
    llm = FakeLLM([TextDelta("Bon"), TextDelta("jour"), Finished("stop", Usage(120, 30))])
    events = collect(llm)
    assert events == [
        ("delta", {"text": "Bon"}),
        ("delta", {"text": "jour"}),
        (
            "done",
            {"finish_reason": "stop", "usage": {"prompt_tokens": 120, "completion_tokens": 30}},
        ),
    ]
    assert llm.calls[0][1] == [{"role": "user", "content": "Salut"}]


def test_done_without_usage() -> None:
    events = collect(FakeLLM([TextDelta("a"), Finished("stop", None)]))
    assert events[-1] == ("done", {"finish_reason": "stop", "usage": None})


def test_app_error_becomes_error_event() -> None:
    llm = FakeLLM(error=AppError(ErrorCode.LLM_UNAVAILABLE, "indisponible", retry_after_seconds=7))
    assert collect(llm) == [
        ("error", {"code": "llm_unavailable", "message": "indisponible", "retry_after_seconds": 7})
    ]


def test_error_after_first_delta_keeps_the_partial_text_event() -> None:
    llm = FakeLLM([TextDelta("Début")], AppError(ErrorCode.LLM_UNAVAILABLE, "coupé"))
    names = [name for name, _ in collect(llm)]
    assert names == ["delta", "error"]


def test_empty_answer_is_an_error() -> None:
    events = collect(FakeLLM([Finished("length", Usage(10, 1500))]))
    assert [(n, d["code"]) for n, d in events] == [("error", "llm_unavailable")]


def test_stream_without_finished_is_an_error() -> None:
    events = collect(FakeLLM([TextDelta("a")]))
    assert [name for name, _ in events] == ["delta", "error"]


def test_unexpected_exception_is_generic_internal_error() -> None:
    events = collect(FakeLLM(error=RuntimeError("secret interne")))
    assert events == [
        (
            "error",
            {
                "code": "internal_error",
                "message": "Erreur interne du serveur.",
                "retry_after_seconds": None,
            },
        )
    ]


def test_system_prompt_gets_the_paris_date() -> None:
    # 23 h 30 UTC le 15 novembre = 0 h 30 le 16 novembre à Paris (heure d'hiver).
    prompt = build_system_prompt(datetime(2026, 11, 15, 23, 30, tzinfo=UTC))
    assert prompt.endswith("Date du jour : 2026-11-16.")
    assert prompt.startswith(load_prompt())


def test_prompt_is_sent_to_the_llm_with_the_date() -> None:
    llm = FakeLLM([TextDelta("a"), Finished("stop", None)])
    collect(llm, now=datetime(2026, 7, 1, 12, 0, tzinfo=UTC))
    assert "Date du jour : 2026-07-01." in llm.calls[0][0]


def test_phase2_prompt_has_no_tools() -> None:
    text = load_prompt()
    assert "Tu es RabonaAI" in text and "CE QUE TU NE FAIS PAS" in text
    assert "get_" not in text and "outil" not in text.lower()
