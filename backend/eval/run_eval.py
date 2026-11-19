"""Harnais d'évaluation (conception §7.6) : exécute le jeu de questions via le service de chat.

Usage, depuis `backend/` (la clé GROQ_API_KEY est lue dans `.env`) :
    uv run python -m eval.run_eval --limit 3
    uv run python -m eval.run_eval --category non_couvert
    uv run python -m eval.run_eval --ids know-001,inj-001 --repeat 2

Chaque passage consomme le quota Groq de l'organisation (≈ 1 300 tokens par question sans outil,
≈ 2 900 avec, mesurés) : le rythme reste sous le plafond de 8 000 TPM et `--max-tokens` coupe
la série au-delà du cumul. Les questions avec outils appellent la vraie API football-data.org.
Les résultats (JSON et rapport Markdown) vont dans `eval/results/` (ignoré par git).
"""

import argparse
import asyncio
import json
import math
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

from app.core.clock import PARIS
from app.core.config import Settings
from app.services.chat import PROMPT_FILE, stream_chat
from app.services.football.tools import (
    MSG_BAD_ARGS,
    MSG_NOT_COVERED,
    MSG_UNAVAILABLE,
    build_football_tools,
)
from app.services.llm.groq import build_groq_client

HERE = Path(__file__).resolve().parent
GOLDEN_SET = HERE / "golden_set.jsonl"
RESULTS_DIR = HERE / "results"

# Phase 3 : les outils existent, les 40 questions sont exécutées (les outils appellent la vraie API
# football-data.org). Mettre False pour ne rejouer que les 26 questions de la phase 2.
TOOLS_AVAILABLE = True
TOOL_ERRORS = {MSG_UNAVAILABLE, MSG_NOT_COVERED, MSG_BAD_ARGS}
RESULT_LINES_IN_REPORT = 25  # lignes d'un retour d'outil recopiées dans le rapport Markdown
TPM_BUDGET = 6000  # tokens/minute : marge sous le plafond Groq de 8 000 (V1)
# Pour ces attentes, aucun chiffre factuel n'est permis hors de la question posée.
NO_NUMBER_EXPECTS = {"decline", "clarify", "redirect", "refuse_injection"}
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
LEAGUE_NAME = re.compile(r"ligue\s*1\b", re.IGNORECASE)  # le « 1 » de Ligue 1 n'est pas un chiffre


def load_questions() -> list[dict]:
    lines = GOLDEN_SET.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def requires_tools(question: dict) -> bool:
    return bool(question["expected_tools"]) or question["category"] == "ambiguite"


def normalize(text: str) -> str:
    """Minuscules, apostrophes et tirets typographiques ramenés à leur forme ASCII."""
    text = text.lower().replace("\u2019", "'")
    for dash in "\u2010\u2011\u2012\u2013\u2014":
        text = text.replace(dash, "-")
    return re.sub(r"(\d)\s*-\s*(\d)", r"\1-\2", text)


def has_decline_phrase(answer: str) -> bool:
    low = normalize(answer)
    return "pas accès" in low or "pas acces" in low


def first_line(answer: str) -> str:
    return next((line for line in answer.splitlines() if line.strip()), "")


def auto_failures(question: dict, answer: str, error: dict | None) -> list[str]:
    """Contrôles automatiques ; liste vide = aucun écart détecté."""
    if error:
        return [f"erreur d'API : {error['code']}"]
    low = normalize(answer)
    failures = [f"absent : {s}" for s in question["must_contain"] if normalize(s) not in low]
    options = question["must_contain_any"]
    if options and not any(normalize(s) in low for s in options):
        failures.append(f"aucun de : {', '.join(options)}")
    failures += [
        f"présent à tort : {s}" for s in question["must_not_contain"] if normalize(s) in low
    ]
    if question["expect"] == "decline" and not has_decline_phrase(first_line(answer)):
        failures.append("« Je n'ai pas accès à cette information » absent de la première ligne")
    if question["expect"] == "clarify" and "?" not in answer:
        failures.append("pas de question de clarification")
    return failures


def tool_failures(question: dict, tool_calls: list[dict]) -> list[str]:
    """Outils et arguments attendus ; un outil en échec invalide aussi la mesure."""
    expected = set(question["expected_tools"])
    called = [call["name"] for call in tool_calls]
    failures = [f"outil attendu absent : {name}" for name in sorted(expected - set(called))]
    failures += [f"outil inattendu : {name}" for name in sorted(set(called) - expected)]
    first = next((c for c in tool_calls if c["name"] in expected), None)
    for key, wanted in (question["expected_args"] or {}).items():
        if first is not None and (first["args"] or {}).get(key) != wanted:
            got = (first["args"] or {}).get(key)
            failures.append(f"argument {key} : obtenu {got!r}, attendu {wanted!r}")
    failures += [
        f"retour d'outil : {c['result']}" for c in tool_calls if c["result"] in TOOL_ERRORS
    ]
    return failures


def ungrounded_numbers(
    question: dict, answer: str, tool_results: list[str] | None = None
) -> list[str]:
    """Nombres de la réponse absents des retours d'outils (ou de la question sans outil) (I)."""
    if tool_results:
        allowed = set(NUMBER.findall("\n".join(tool_results)))
    elif question["expect"] in NO_NUMBER_EXPECTS:
        allowed = set(NUMBER.findall(question["question"]))
    else:
        return []
    return sorted(set(NUMBER.findall(LEAGUE_NAME.sub("", answer))) - allowed)


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p * len(ordered)) - 1)]


class RecordingToolbox:
    """Enveloppe les outils réels et garde la trace des appels (nom, arguments, retour)."""

    def __init__(self, toolbox) -> None:
        self._toolbox = toolbox
        self.definitions = toolbox.definitions
        self.calls: list[dict] = []

    async def run(self, name: str, arguments: str):
        result = await self._toolbox.run(name, arguments)
        self.calls.append({"name": name, "args": result.args, "result": result.text})
        return result


async def ask(llm, toolbox, question: dict) -> dict:
    started = time.perf_counter()
    parts: list[str] = []
    row: dict = {"ttft": None, "usage": None, "finish_reason": None, "error": None}
    recorder = RecordingToolbox(toolbox)
    async for name, data in stream_chat(llm, question["question"], recorder):
        if name == "delta":
            if row["ttft"] is None:
                row["ttft"] = time.perf_counter() - started
            parts.append(data["text"])
        elif name == "done":
            row["usage"], row["finish_reason"] = data["usage"], data["finish_reason"]
        elif name == "error":
            row["error"] = data
    row["answer"] = "".join(parts)
    row["seconds"] = time.perf_counter() - started
    row["tool_calls"] = recorder.calls
    return row


def summarize(rows: list[dict], interrupted: str | None) -> dict:
    tokens = [r["tokens"] for r in rows if r["tokens"]]
    ttfts = [r["ttft"] for r in rows if r["ttft"] is not None]
    auto = [r for r in rows if r["review"] == "auto"]
    declines = [r for r in rows if r["expect"] == "decline" and not r["error"]]
    checked = [
        r for r in rows if (r["expect"] in NO_NUMBER_EXPECTS or r["tool_calls"]) and not r["error"]
    ]
    tooled = [r for r in rows if r["expected_tools"]]
    respected = sum(1 for r in declines if not r["failures"] and not r["ungrounded"])
    return {
        "executions": len(rows),
        "interrupted": interrupted,
        "api_errors": sum(1 for r in rows if r["error"]),
        "auto_ok": f"{sum(1 for r in auto if not r['failures'])}/{len(auto)}",
        "to_review_manually": sum(1 for r in rows if r["review"] == "manual"),
        "decline_respected": f"{respected}/{len(declines)}",
        "tool_accuracy": f"{sum(1 for r in tooled if not r['tool_failures'])}/{len(tooled)}",
        "ungrounded_numbers": f"{sum(1 for r in checked if r['ungrounded'])}/{len(checked)}",
        "total_tokens": sum(tokens),
        "tokens_mean": round(statistics.mean(tokens)) if tokens else None,
        "tokens_p95": percentile(tokens, 0.95),
        "ttft_median": round(statistics.median(ttfts), 2) if ttfts else None,
        "ttft_p95": round(percentile(ttfts, 0.95), 2) if ttfts else None,
    }


def write_report(stamp: str, meta: dict, summary: dict, rows: list[dict]) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    payload = {"meta": meta, "summary": summary, "rows": rows}
    (RESULTS_DIR / f"{stamp}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        f"# Évaluation {stamp}",
        "",
        f"Modèle : `{meta['model']}` — prompt : `{meta['prompt']}`",
        "",
    ]
    lines += ["| Métrique | Valeur |", "|---|---|"]
    lines += [f"| {key} | {value} |" for key, value in summary.items()]
    lines += ["", "## Réponses", ""]
    for r in rows:
        verdict = (
            "à relire" if r["review"] == "manual" else ("OK" if not r["failures"] else "ÉCART")
        )
        lines += [
            f"### {r['id']} — {r['category']} — {verdict}",
            "",
            f"**Question :** {r['question']}",
            "",
        ]
        if r["notes"]:
            lines += [f"*Attendu : {r['notes']}*", ""]
        if r["failures"]:
            lines += [f"**Écarts :** {' ; '.join(r['failures'])}", ""]
        for call in r["tool_calls"]:
            shown = call["result"].splitlines()[:RESULT_LINES_IN_REPORT]
            lines += [
                f"**Outil :** `{call['name']}` {json.dumps(call['args'], ensure_ascii=False)}",
                "",
            ]
            lines += ["```text", *shown, "```", ""]
        if r["ungrounded"]:
            lines += [f"**Chiffres hors source :** {', '.join(r['ungrounded'])}", ""]
        answer = r["answer"] or f"(aucune réponse : {r['error']})"
        lines += ["> " + line for line in answer.splitlines()] + [""]
        if r["review"] == "manual":
            lines += ["- [ ] relu : conforme", ""]
    path = RESULTS_DIR / f"{stamp}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    llm = build_groq_client(settings)
    if llm is None:
        print("GROQ_API_KEY absente : renseigne-la dans backend/.env.")
        return 1
    football_key = settings.football_data_api_key
    if TOOLS_AVAILABLE and football_key is None:
        print("FOOTBALL_DATA_API_KEY absente : renseigne-la dans backend/.env.")
        return 1
    toolbox = build_football_tools(football_key.get_secret_value() if football_key else None)
    questions = load_questions()
    if not TOOLS_AVAILABLE:
        questions = [q for q in questions if not requires_tools(q)]
    if args.ids:
        wanted = set(args.ids.split(","))
        questions = [q for q in questions if q["id"] in wanted]
    if args.category:
        questions = [q for q in questions if q["category"] == args.category]
    if args.limit:
        questions = questions[: args.limit]
    if not questions:
        print("Aucune question sélectionnée.")
        return 1
    print(f"{len(questions) * args.repeat} exécutions, modèle {settings.groq_model}")

    rows: list[dict] = []
    total = 0
    interrupted: str | None = None
    for _ in range(args.repeat):
        for q in questions:
            if total >= args.max_tokens:
                interrupted = f"plafond --max-tokens atteint ({total} tokens)"
                break
            result = await ask(llm, toolbox, q)
            usage = result["usage"]
            tokens = usage["prompt_tokens"] + usage["completion_tokens"] if usage else 0
            total += tokens
            row = {
                "id": q["id"], "category": q["category"], "question": q["question"],
                "expect": q["expect"], "review": q["review"], "notes": q["notes"],
                "answer": result["answer"], "error": result["error"], "tokens": tokens,
                "ttft": result["ttft"], "finish_reason": result["finish_reason"],
                "expected_tools": q["expected_tools"], "tool_calls": result["tool_calls"],
                "tool_failures": tool_failures(q, result["tool_calls"]),
                "ungrounded": ungrounded_numbers(
                    q, result["answer"], [c["result"] for c in result["tool_calls"]]
                ),
            }  # fmt: skip
            row["failures"] = (
                auto_failures(q, result["answer"], result["error"]) + row["tool_failures"]
            )
            rows.append(row)
            mark = (
                "ERREUR"
                if row["error"]
                else (
                    "à relire"
                    if q["review"] == "manual"
                    else ("OK" if not row["failures"] else "ÉCART")
                )
            )
            print(f"  [{mark}] {q['id']} | {tokens} tokens | {row['failures'] or ''}")
            if row["error"] and row["error"]["code"] == "quota_global_daily":
                interrupted = "limite quotidienne Groq atteinte"
                break
            if tokens:  # rythme : rester sous TPM_BUDGET tokens par minute
                await asyncio.sleep(max(0.0, tokens * 60 / TPM_BUDGET - result["seconds"]))
        if interrupted:
            break

    await toolbox.aclose()
    stamp = datetime.now(PARIS).strftime("%Y%m%d-%H%M%S")
    summary = summarize(rows, interrupted)
    meta = {"model": settings.groq_model, "prompt": PROMPT_FILE.name, "repeat": args.repeat}
    report = write_report(stamp, meta, summary, rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Rapport : {report}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ids", help="identifiants séparés par des virgules")
    parser.add_argument("--category")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=100_000)
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
