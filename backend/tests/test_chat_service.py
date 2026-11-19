import asyncio
from datetime import UTC, datetime

from app.core.errors import AppError, ErrorCode
from app.services.chat import MAX_TOOL_CALLS, build_system_prompt, load_prompt, stream_chat
from app.services.llm.base import Finished, TextDelta, ToolCall, ToolCallsRequested, Usage
from app.services.toolbox import ToolResult


class FakeLLM:
    """Client LLM scripté : un seul flux, aucun réseau."""

    def __init__(self, events=(), error: Exception | None = None) -> None:
        self.events = list(events)
        self.error = error
        self.calls: list[tuple[str, list[dict], list | None]] = []

    async def stream(self, system, messages, tools=None):
        self.calls.append((system, list(messages), tools))
        for event in self.events:
            yield event
        if self.error:
            raise self.error


class ScriptedLLM:
    """Un flux d'événements par appel : tour 1 (outils demandés), tour 2 (réponse)."""

    def __init__(self, *rounds) -> None:
        self.rounds = list(rounds)
        self.calls: list[tuple[str, list[dict], list | None]] = []

    async def stream(self, system, messages, tools=None):
        self.calls.append((system, list(messages), tools))
        for event in self.rounds[len(self.calls) - 1]:
            yield event


class FakeToolbox:
    definitions: list[dict] = [{"type": "function", "function": {"name": "get_standings"}}]  # noqa: RUF012

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def run(self, name: str, arguments: str) -> ToolResult:
        self.calls.append((name, arguments))
        return ToolResult(f"retour de {name}", {})


def collect(llm, message="Salut", toolbox=None, now=None):
    async def run():
        return [item async for item in stream_chat(llm, message, toolbox, now)]

    return asyncio.run(run())


def call(call_id="c1", name="get_standings", arguments='{"competition":"ligue-1"}') -> ToolCall:
    return ToolCall(call_id, name, arguments)


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
    assert llm.calls[0][2] is None  # pas d'outils fournis : aucune définition envoyée


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
    assert [name for name, _ in collect(llm)] == ["delta", "error"]


def test_empty_answer_is_an_error() -> None:
    events = collect(FakeLLM([Finished("length", Usage(10, 1500))]))
    assert [(n, d["code"]) for n, d in events] == [("error", "llm_unavailable")]


def test_stream_without_finished_is_an_error() -> None:
    assert [name for name, _ in collect(FakeLLM([TextDelta("a")]))] == ["delta", "error"]


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


def test_final_prompt_describes_the_tools_and_the_rules() -> None:
    text = load_prompt()
    for expected in ("get_standings", "get_matches", "get_top_scorers", "Tutoie", "sans tableau"):
        assert expected in text


# ---------------------------------------------------------------- tour d'outils


def test_tool_round_trip() -> None:
    llm = ScriptedLLM(
        [ToolCallsRequested((call(),)), Finished("tool_calls", Usage(400, 30))],
        [TextDelta("Voici"), TextDelta(" le classement"), Finished("stop", Usage(700, 60))],
    )
    toolbox = FakeToolbox()
    events = collect(llm, "Classement Ligue 1 ?", toolbox)
    assert events == [
        ("status", {"tool": "get_standings", "state": "running"}),
        ("delta", {"text": "Voici"}),
        ("delta", {"text": " le classement"}),
        (
            "done",
            {"finish_reason": "stop", "usage": {"prompt_tokens": 1100, "completion_tokens": 90}},
        ),
    ]
    assert toolbox.calls == [("get_standings", '{"competition":"ligue-1"}')]
    # Les définitions sont envoyées aux deux tours ; le second tour voit l'appel et son retour.
    assert [c[2] for c in llm.calls] == [toolbox.definitions, toolbox.definitions]
    assert llm.calls[1][1][1:] == [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "get_standings", "arguments": '{"competition":"ligue-1"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "retour de get_standings"},
    ]


def test_tool_calls_are_capped() -> None:
    requested = tuple(call(f"c{i}") for i in range(MAX_TOOL_CALLS + 2))
    llm = ScriptedLLM(
        [ToolCallsRequested(requested), Finished("tool_calls", None)],
        [TextDelta("ok"), Finished("stop", None)],
    )
    toolbox = FakeToolbox()
    events = collect(llm, toolbox=toolbox)
    assert len(toolbox.calls) == MAX_TOOL_CALLS
    assert [n for n, _ in events].count("status") == MAX_TOOL_CALLS
    second_round = llm.calls[1][1]
    assert len(second_round[1]["tool_calls"]) == MAX_TOOL_CALLS
    assert [m["role"] for m in second_round[2:]] == ["tool"] * MAX_TOOL_CALLS


def test_second_tool_request_is_ignored_and_empty_answer_is_an_error() -> None:
    llm = ScriptedLLM(
        [ToolCallsRequested((call(),)), Finished("tool_calls", None)],
        [ToolCallsRequested((call("c2"),)), Finished("tool_calls", None)],
    )
    toolbox = FakeToolbox()
    events = collect(llm, toolbox=toolbox)
    assert len(toolbox.calls) == 1  # pas de second tour d'outils
    assert [(n, d.get("code")) for n, d in events] == [
        ("status", None),
        ("error", "llm_unavailable"),
    ]


def test_tool_request_without_toolbox_is_ignored() -> None:
    llm = ScriptedLLM([TextDelta("Réponse"), ToolCallsRequested((call(),)), Finished("stop", None)])
    events = collect(llm)
    assert [n for n, _ in events] == ["delta", "done"]
    assert len(llm.calls) == 1


def test_text_before_the_tool_call_is_kept_in_the_assistant_message() -> None:
    llm = ScriptedLLM(
        [TextDelta("Je regarde."), ToolCallsRequested((call(),)), Finished("tool_calls", None)],
        [TextDelta("Voilà"), Finished("stop", None)],
    )
    collect(llm, toolbox=FakeToolbox())
    assert llm.calls[1][1][1]["content"] == "Je regarde."
