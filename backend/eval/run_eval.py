"""Harnais d'évaluation (conception §7.6) : exécute le jeu de questions via le service de chat.

Usage, depuis `backend/` (la clé GROQ_API_KEY est lue dans `.env`) :
    uv run python -m eval.run_eval --limit 3
    uv run python -m eval.run_eval --category non_couvert
    uv run python -m eval.run_eval --ids know-001,inj-001 --repeat 2

Chaque passage consomme le quota Groq de l'organisation (≈ 650 tokens par question, mesuré) :
le rythme reste sous le plafond de 8 000 TPM et `--max-tokens` coupe la série au-delà du cumul.
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

from app.core.config import Settings
from app.services.chat import PARIS, PROMPT_FILE, stream_chat
from app.services.llm.groq import build_groq_client

HERE = Path(__file__).resolve().parent
GOLDEN_SET = HERE / "golden_set.jsonl"
RESULTS_DIR = HERE / "results"

# Phase 2 : pas d'outils. Passer à True en phase 3 pour exécuter aussi les 14 questions
# qui en dépendent (outils attendus, et questions d'ambiguïté qui supposent les outils).
TOOLS_AVAILABLE = False
TPM_BUDGET = 6000  # tokens/minute : marge sous le plafond Groq de 8 000 (V1)
# Pour ces attentes, aucun chiffre factuel n'est permis hors de la question posée.
NO_NUMBER_EXPECTS = {"decline", "clarify", "redirect", "refuse_injection"}
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


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


def ungrounded_numbers(question: dict, answer: str) -> list[str]:
    """Nombres de la réponse absents de la question (heuristique, I)."""
    if question["expect"] not in NO_NUMBER_EXPECTS:
        return []
    allowed = set(NUMBER.findall(question["question"]))
    return sorted(set(NUMBER.findall(answer)) - allowed)


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p * len(ordered)) - 1)]


async def ask(llm, question: dict) -> dict:
    started = time.perf_counter()
    parts: list[str] = []
    row: dict = {"ttft": None, "usage": None, "finish_reason": None, "error": None}
    async for name, data in stream_chat(llm, question["question"]):
        if name == "delta":
            if row["ttft"] is None:
                row["ttft"] = time.perf_counter() - started
            parts.append(data["text"])
        elif name == "done":
            row["usage"], row["finish_reason"] = data["usage"], data["finish_reason"]
        else:
            row["error"] = data
    row["answer"] = "".join(parts)
    row["seconds"] = time.perf_counter() - started
    return row


def summarize(rows: list[dict], interrupted: str | None) -> dict:
    tokens = [r["tokens"] for r in rows if r["tokens"]]
    ttfts = [r["ttft"] for r in rows if r["ttft"] is not None]
    auto = [r for r in rows if r["review"] == "auto"]
    declines = [r for r in rows if r["expect"] == "decline" and not r["error"]]
    checked = [r for r in rows if r["expect"] in NO_NUMBER_EXPECTS and not r["error"]]
    respected = sum(1 for r in declines if not r["failures"] and not r["ungrounded"])
    return {
        "executions": len(rows),
        "interrupted": interrupted,
        "api_errors": sum(1 for r in rows if r["error"]),
        "auto_ok": f"{sum(1 for r in auto if not r['failures'])}/{len(auto)}",
        "to_review_manually": sum(1 for r in rows if r["review"] == "manual"),
        "decline_respected": f"{respected}/{len(declines)}",
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
        if r["ungrounded"]:
            lines += [f"**Chiffres hors question :** {', '.join(r['ungrounded'])}", ""]
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
            result = await ask(llm, q)
            usage = result["usage"]
            tokens = usage["prompt_tokens"] + usage["completion_tokens"] if usage else 0
            total += tokens
            row = {
                "id": q["id"], "category": q["category"], "question": q["question"],
                "expect": q["expect"], "review": q["review"], "notes": q["notes"],
                "answer": result["answer"], "error": result["error"], "tokens": tokens,
                "ttft": result["ttft"], "finish_reason": result["finish_reason"],
                "failures": auto_failures(q, result["answer"], result["error"]),
                "ungrounded": ungrounded_numbers(q, result["answer"]),
            }  # fmt: skip
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
