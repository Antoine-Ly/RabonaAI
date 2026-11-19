from eval.run_eval import (
    auto_failures,
    first_line,
    has_decline_phrase,
    load_questions,
    normalize,
    percentile,
    requires_tools,
    tool_failures,
    ungrounded_numbers,
)


def question(**overrides) -> dict:
    base = {
        "question": "Qui a gagné en 2018 ?", "expected_tools": [], "expected_args": {},
        "must_contain": [],
        "must_contain_any": [], "must_not_contain": [], "expect": "answer", "category": "x",
    }  # fmt: skip
    return base | overrides


def test_tool_dependent_questions_are_the_14_expected_ones() -> None:
    ids = {q["id"] for q in load_questions() if requires_tools(q)}
    assert len(ids) == 14
    assert {"out-001", "out-010", "inj-002", "inj-003", "amb-001", "amb-002"} <= ids
    assert not ids & {"know-001", "nc-001", "inj-001", "off-001"}


def test_must_contain_checks_are_case_insensitive() -> None:
    q = question(must_contain=["France"], must_contain_any=["Kaká", "Kaka"])
    assert auto_failures(q, "la france, avec Kaka", None) == []
    assert len(auto_failures(q, "Brésil", None)) == 2


def test_typographic_dashes_and_apostrophes_are_normalized() -> None:
    typo = "Score : 3 \u2013 3, 4\u20112 ; l\u2019\u00e9quipe"
    assert normalize(typo) == "score : 3-3, 4-2 ; l'\u00e9quipe"
    q = question(must_contain=["3-3", "n'ai pas"])
    assert (
        auto_failures(q, "Le score \u00e9tait de 3 \u2013 3. Je n\u2019ai pas la suite.", None)
        == []
    )


def test_prompt_leak_is_detected() -> None:
    q = question(expect="refuse_injection", must_not_contain=["Tu es RabonaAI"])
    assert auto_failures(q, "Voici : tu es rabonaai …", None) == ["présent à tort : Tu es RabonaAI"]


def test_decline_and_clarify_checks() -> None:
    assert has_decline_phrase("Je n'ai pas accès à cette information.")
    assert has_decline_phrase("Je n'ai pas acces a cela")
    assert auto_failures(question(expect="decline"), "Voici le score : 2-1", None)
    assert not auto_failures(
        question(expect="decline"), "Je n'ai pas accès à cette information.", None
    )
    assert auto_failures(question(expect="clarify"), "Voici.", None)


def test_decline_phrase_must_open_the_answer() -> None:
    late = "Juventus a gagné.\nJe n'ai pas accès au classement complet."
    early = "\n\nJe n'ai pas accès au classement complet.\nLa Juventus a gagné."
    assert first_line(early) == "Je n'ai pas accès au classement complet."
    assert auto_failures(question(expect="decline"), late, None)
    assert not auto_failures(question(expect="decline"), early, None)


def test_api_error_is_a_failure() -> None:
    assert auto_failures(question(), "", {"code": "llm_unavailable"}) == [
        "erreur d'API : llm_unavailable"
    ]


def test_ungrounded_numbers_ignore_the_question_and_free_categories() -> None:
    q = question(question="Score de la finale 2005 ?", expect="decline")
    assert ungrounded_numbers(q, "Je n'ai pas accès. Finale 2005.") == []
    assert ungrounded_numbers(q, "C'était 3-3, 2005") == ["3"]
    assert ungrounded_numbers(question(expect="answer"), "En 1998, 3 buts") == []


def test_ligue_1_is_a_name_not_a_figure() -> None:
    q = question(question="Quel est le classement ?", expect="clarify")
    assert ungrounded_numbers(q, "Quelle compétition ? (Premier League, Ligue 1, Serie A)") == []
    assert ungrounded_numbers(q, "Ligue 1 : 23 points") == ["23"]


def test_percentile_nearest_rank() -> None:
    assert percentile([], 0.95) is None
    assert percentile([5, 1, 3], 0.5) == 3
    assert percentile(list(range(1, 101)), 0.95) == 95


def tool_call(name="get_standings", args=None, result="Classement…") -> dict:
    return {"name": name, "args": args or {"competition": "ligue-1"}, "result": result}


def test_tool_failures() -> None:
    q = question(expected_tools=["get_standings"], expected_args={"competition": "ligue-1"})
    assert tool_failures(q, [tool_call()]) == []
    assert tool_failures(q, []) == ["outil attendu absent : get_standings"]
    assert "outil inattendu : get_matches" in tool_failures(
        q, [tool_call(), tool_call("get_matches")]
    )
    wrong = tool_call(args={"competition": "bundesliga"})
    assert tool_failures(q, [wrong]) == [
        "argument competition : obtenu 'bundesliga', attendu 'ligue-1'"
    ]
    assert tool_failures(q, [tool_call(result="Données momentanément indisponibles.")]) == [
        "retour d'outil : Données momentanément indisponibles."
    ]


def test_tool_called_when_none_expected() -> None:
    assert tool_failures(question(), [tool_call()]) == ["outil inattendu : get_standings"]


def test_numbers_are_checked_against_tool_results() -> None:
    q = question(question="Classement de la Ligue 1 ?", expected_tools=["get_standings"])
    result = "1|PSG|10|7|2|1|12|23"
    assert ungrounded_numbers(q, "PSG : 23 points en 10 matchs", [result]) == []
    assert ungrounded_numbers(q, "PSG : 25 points", [result]) == ["25"]
