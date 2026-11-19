"""Garde-fous sur les fichiers de référence : prompt système et jeu d'évaluation."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEAK_MARKERS = ["Tu es RabonaAI", "CE QUE TU NE FAIS PAS", "DONNÉES VÉRIFIÉES"]
COMPETITION_SLUGS = {
    "premier-league", "championship", "la-liga", "serie-a", "bundesliga",
    "ligue-1", "eredivisie", "primeira-liga", "champions-league", "brasileirao",
}  # fmt: skip


def test_system_prompt_contains_leak_markers() -> None:
    text = (ROOT / "app/prompts/football_system_prompt.md").read_text(encoding="utf-8")
    for marker in LEAK_MARKERS:
        assert marker in text


def test_golden_set_is_valid() -> None:
    lines = (ROOT / "eval/golden_set.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    assert len(rows) == 40
    assert len({r["id"] for r in rows}) == 40
    for r in rows:
        assert {"id", "category", "question", "expected_tools", "expect"} <= r.keys()
        args = r["expected_args"]
        if args and "competition" in args:
            assert args["competition"] in COMPETITION_SLUGS
