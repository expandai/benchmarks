from __future__ import annotations

from collections import Counter

import pytest

from aastirrup.omniscience import (
    CORRECT,
    GRADER_PROMPT,
    INCORRECT,
    NOT_ATTEMPTED,
    PARTIAL,
    Question,
    answerer_system_prompt,
    grader_prompt,
    load_questions,
    parse_grade,
    sample_questions,
    score,
)

Q = Question("aao-001", 1, "Finance", "Accounting", "Accounting", "What is {x}?", "ASC 606-10-25-15")


@pytest.mark.parametrize(
    ("reply", "grade"),
    [
        ("A", CORRECT),
        (" b\n", INCORRECT),
        ("“C”", PARTIAL),
        ("D.", NOT_ATTEMPTED),
        ("CORRECT", CORRECT),
        ("A: CORRECT", CORRECT),
        ("The grade is NOT_ATTEMPTED", NOT_ATTEMPTED),
        ("PARTIAL_ANSWER", PARTIAL),
    ],
)
def test_parse_grade(reply: str, grade: str) -> None:
    assert parse_grade(reply) == grade


def test_parse_grade_rejects_junk() -> None:
    with pytest.raises(ValueError):
        parse_grade("no idea")


def test_score_matches_paper_formulas() -> None:
    grades = [CORRECT] * 6 + [INCORRECT] * 2 + [PARTIAL] * 1 + [NOT_ATTEMPTED] * 1
    result = score(grades)
    assert result["omniscience_index"] == pytest.approx(100 * (6 - 2) / 10)
    assert result["accuracy"] == pytest.approx(60.0)
    assert result["hallucination_rate"] == pytest.approx(100 * 2 / 4)
    assert score([])["omniscience_index"] is None
    assert score([CORRECT])["hallucination_rate"] is None
    assert score([INCORRECT, INCORRECT])["omniscience_index"] == -100.0


def test_prompts() -> None:
    system = answerer_system_prompt(Q)
    assert system.startswith("You are answering questions about Finance, and in particular Accounting.\n")
    assert "it is better that you say this than get the wrong answer." in system
    graded = grader_prompt(Q, "ASC 606-10-25-15 {braces}")
    assert "Question: What is {x}? \nGold target: ASC 606-10-25-15 \nPredicted answer: ASC 606-10-25-15 {braces} " in graded
    assert GRADER_PROMPT.count("{question}") == 1 and "{" not in graded.replace("{x}", "").replace("{braces}", "")
    assert graded.endswith("with no text around it.")
    assert "D: NOT_ATTEMPTED \n\nJust return" in graded


def test_load_and_sample_are_deterministic_and_domain_balanced() -> None:
    questions = load_questions()
    assert len(questions) == 600
    first = sample_questions(questions, 20, 20261026)
    again = sample_questions(list(reversed(questions)), 20, 20261026)
    assert [q.id for q in first] == [q.id for q in again]
    assert len({q.id for q in first}) == 20
    assert sorted(Counter(q.domain for q in first).values()) == [3, 3, 3, 3, 4, 4]
    assert [q.id for q in sample_questions(questions, 20, 1)] != [q.id for q in first]
    full = sample_questions(questions, 600, 7)
    assert len({q.id for q in full}) == 600


def test_grader_prompt_is_the_paper_text() -> None:
    import hashlib

    from aastirrup import omniscience

    # SHA-256 of appendix A.2 as extracted from https://arxiv.org/html/2511.13029v1 (em-space indents -> " ").
    digest = hashlib.sha256(omniscience.GRADER_PROMPT.encode("utf-8")).hexdigest()
    assert digest == "01e706e6c3a33d0091399c4dd854997f0a06a1b0afafdc801471c18fec951e72"
