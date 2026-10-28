"""AA-Omniscience: questions, prompts, grade parsing and scoring, as Artificial Analysis publishes them.

Sources (checked 2026-10-26):

* Prompts and scoring: Jackson et al., "AA-Omniscience: Evaluating Cross-Domain Knowledge Reliability in
  Large Language Models", arXiv 2511.13029v1, section 2.4 and appendix A
  (https://arxiv.org/html/2511.13029v1). ``ANSWERER_SYSTEM_PROMPT`` is appendix A.1 and ``GRADER_PROMPT``
  is appendix A.2, verbatim (trailing spaces and typographic quotes kept).
* Search-API setting: https://artificialanalysis.ai/methodology/search-api (grader GPT-5.6 Luna (medium)).

Questions come from the bakeoff's pinned loader (``bakeoff.suites.load_aa_omniscience``: the public 600,
SHA-256 checked), imported, not copied.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Appendix A.1 wording, with the historical runs' mapping: {topic} = the CSV's ``domain`` and
# {category} = its ``topic``. This differs from the pinned dataset card's domain/subtopic prompt:
# ``topic`` and ``subtopic`` differ in 545 of 600 questions. Preserve this mapping for those runs;
# adopting the card's mapping requires a new protocol version and a separate run.
ANSWERER_SYSTEM_PROMPT = (
    "You are answering questions about {topic}, and in particular {category}.\n"
    "You will be given a question, answer with JUST the answer (no explanation).\n"
    "If you do not know the answer, or you need more context or tools to answer the question,\n"
    "be clear about this - it is better that you say this than get the wrong answer."
)

# Appendix A.2, verbatim from the arXiv HTML (trailing spaces kept; its nine em-space indents written as one
# space). Kept in a text file so editors cannot strip the trailing whitespace.
GRADER_PROMPT = (Path(__file__).with_name("grader_prompt.txt")).read_text(encoding="utf-8")

# The user turn of the agent run. AA does not publish the agent prompt; this is our choice (README).
TASK_TEMPLATE = (
    "Question: {question}\n\n"
    "Use web_search (and web_fetch on URLs it returned) as needed. When you are done, call the finish tool "
    "with your final answer in `answer`: JUST the answer, no explanation. If you could not find or work out "
    "the answer, say so in `answer` instead of guessing."
)

CORRECT = "CORRECT"
INCORRECT = "INCORRECT"
PARTIAL = "PARTIAL_ANSWER"
NOT_ATTEMPTED = "NOT_ATTEMPTED"
GRADES = (CORRECT, INCORRECT, PARTIAL, NOT_ATTEMPTED)
_LETTERS = {"A": CORRECT, "B": INCORRECT, "C": PARTIAL, "D": NOT_ATTEMPTED}


@dataclass(frozen=True)
class Question:
    id: str
    question_id: int
    domain: str
    topic: str
    subtopic: str
    question: str
    answer: str


def load_questions() -> list[Question]:
    """The public 600, via the bakeoff's pinned, SHA-256-checked loader."""
    from bakeoff.suites import load_aa_omniscience

    return [
        Question(
            id=task.id,
            question_id=int(task.id.split("-")[1]),
            domain=task.metadata["domain"],
            topic=task.metadata["topic"],
            subtopic=task.metadata["subtopic"],
            question=task.problem,
            answer=task.answer,
        )
        for task in load_aa_omniscience()
    ]


def sample_questions(questions: list[Question], n: int, seed: int) -> list[Question]:
    """Domain-balanced sample: shuffle each domain with ``seed``, then deal domains round-robin (sorted).

    With 6 domains and n=20 that is 4+4+3+3+3+3. Order of the result is the dealing order.
    """
    by_domain: dict[str, list[Question]] = {}
    for question in sorted(questions, key=lambda q: q.question_id):
        by_domain.setdefault(question.domain, []).append(question)
    rng = random.Random(seed)
    for domain in sorted(by_domain):
        rng.shuffle(by_domain[domain])
    picked: list[Question] = []
    depth = 0
    while len(picked) < n:
        added = False
        for domain in sorted(by_domain):
            if depth < len(by_domain[domain]) and len(picked) < n:
                picked.append(by_domain[domain][depth])
                added = True
        if not added:
            break
        depth += 1
    return picked


def answerer_system_prompt(question: Question) -> str:
    return ANSWERER_SYSTEM_PROMPT.format(topic=question.domain, category=question.topic)


def task_prompt(question: Question) -> str:
    return TASK_TEMPLATE.format(question=question.question)


def grader_prompt(question: Question, predicted_answer: str) -> str:
    # str.replace, not format: the prompt contains literal braces-free text but answers may contain braces.
    return (
        GRADER_PROMPT.replace("{question}", question.question)
        .replace("{target}", question.answer)
        .replace("{predicted_answer}", predicted_answer)
    )


def parse_grade(text: str) -> str:
    """Map the grader's reply to a grade. Accepts a bare letter (as instructed) or a grade word."""
    cleaned = text.strip().strip("\"'“”`*. ").upper()
    if cleaned in _LETTERS:
        return _LETTERS[cleaned]
    if cleaned in GRADES:
        return cleaned
    match = re.match(r"^([ABCD])\b", cleaned)
    if match:
        return _LETTERS[match.group(1)]
    for grade in (PARTIAL, NOT_ATTEMPTED, INCORRECT, CORRECT):  # longest/most specific first
        if grade in cleaned:
            return grade
    raise ValueError(f"unparseable grade: {text[:200]!r}")


def score(grades: list[str]) -> dict[str, Any]:
    """Omniscience Index, accuracy and hallucination rate (paper section 2.4).

    OI = 100 * (c - i) / (c + p + i + a); accuracy = c / N; hallucination rate = i / (p + i + a).
    No domain weighting (the paper defines none; AA's search-API sample is balanced 100 per domain).
    """
    counts = Counter(grades)
    c, i, p, a = (counts[CORRECT], counts[INCORRECT], counts[PARTIAL], counts[NOT_ATTEMPTED])
    total = c + i + p + a
    not_correct = p + i + a
    return {
        "n": total,
        "correct": c,
        "incorrect": i,
        "partial": p,
        "not_attempted": a,
        "omniscience_index": 100.0 * (c - i) / total if total else None,
        "accuracy": 100.0 * c / total if total else None,
        "hallucination_rate": 100.0 * i / not_correct if not_correct else None,
    }
