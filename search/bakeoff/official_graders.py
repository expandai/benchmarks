"""The designers' own graders for FRAMES, SimpleQA Verified and SealQA.

Each grader sends the official prompt (``official_prompts.py``, verbatim) to the official
judge model through the harness ``Judge`` machinery, parses the reply the way the official
code does (with the two SealQA notebook defects fixed, below) and returns a ``Grade`` whose
``scores`` carry the one-hot label plus the per-task inputs of the official metric.

Judge models (OpenRouter ids; ``METHODOLOGY.md`` §§4–6):

* FRAMES: Gemini-Pro-1.5-0514 is retired. Substitute ``openai/gpt-4.1`` (Perplexity's
  precedent in ``search_evals``). Figure 6 prompt, free text, last ``Decision:`` wins.
* SimpleQA Verified: ``gpt-4.1-2025-04-14``. OpenRouter lists no dated id, so the alias
  ``openai/gpt-4.1`` is used and the model string the response reports is stored per grade
  (``judge_model_reported``). Appendix A prompt as one user message, letter A/B/C.
* SealQA: ``openai/gpt-4o-mini``, temperature 0, ``max_tokens`` 1024, Appendix C prompt as
  one user message, letter A/B/C.

Fixes to the SealQA Colab that are deliberate deviations: (1) the notebook's ``grading()``
indexes ``raw_response['output']`` on a ``str`` and raises as published — irrelevant here;
(2) its ``re.search(r"(A|B|C)")`` takes the first capital letter anywhere, so a reply of
``CORRECT`` parses as C = NOT_ATTEMPTED. ``parse_letter`` anchors the letter at the start of
the reply, accepts the full-word label as a fallback, and raises on anything else so the
call is retried (``PARSE_ATTEMPTS``) and then fails loudly instead of silently defaulting.

Metrics (``simpleqa_verified_metrics``): per simple-evals, ``accuracy_given_attempted =
correct / (correct + incorrect)`` and ``f1 = 2 · acc_att · acc / (acc_att + acc)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from benchmarks.graders.base import JudgeSpend, is_blank
from harness.llm.judge import Judge, JudgeOutputError, JudgeResponse, _ACTIVE_USAGE
from harness.llm.pricing import ModelPrice, register_price
from harness.suite import Grade

from .official_prompts import (
    FRAMES_FIG6_SYSTEM,
    FRAMES_FIG6_USER,
    SEALQA_GRADER,
    SIMPLEQA_VERIFIED_GRADER,
)

Label = Literal["CORRECT", "INCORRECT", "NOT_ATTEMPTED"]

FRAMES_JUDGE = "openai/gpt-4.1"
SIMPLEQA_VERIFIED_JUDGE = "openai/gpt-4.1"  # = gpt-4.1-2025-04-14 on OpenAI; no dated id on OpenRouter
SEALQA_JUDGE = "openai/gpt-4o-mini"
SEALQA_JUDGE_TEMPERATURE = 0.0
SEALQA_JUDGE_MAX_TOKENS = 1024
PARSE_ATTEMPTS = 3

# List prices (USD per 1M tokens, OpenRouter 2026-10-26) so the harness's own pricing table can
# price these judges if OpenRouter ever omits ``usage.cost``.
register_price("openai/gpt-4.1", ModelPrice(2.00, 8.00, 0.50))
register_price("openai/gpt-4o-mini", ModelPrice(0.15, 0.60, 0.075))

LETTER_TO_LABEL: dict[str, Label] = {"A": "CORRECT", "B": "INCORRECT", "C": "NOT_ATTEMPTED"}
_LETTER = re.compile(r"^\s*\(?([ABC])\)?(?![A-Za-z])")
_WORD = re.compile(r"^\s*(CORRECT|INCORRECT|NOT[ _]ATTEMPTED)\b", re.I)
_DECISION = re.compile(r"Decision:?\"?\**:?\s*[\"*]*\s*(TRUE|FALSE)\b", re.I)


def parse_letter(reply: str) -> Label:
    """A/B/C anchored at the start of the reply; full-word labels accepted as a fallback."""
    match = _LETTER.match(reply)
    if match:
        return LETTER_TO_LABEL[match.group(1)]
    word = _WORD.match(reply)
    if word:
        return word.group(1).upper().replace(" ", "_")  # type: ignore[return-value]
    raise ValueError(f"no A/B/C grade at the start of the judge reply: {reply[:120]!r}")


def parse_decision(reply: str) -> bool:
    """FRAMES Figure 6: the last ``Decision:`` value; TRUE means correct."""
    found = _DECISION.findall(reply)
    if not found:
        raise ValueError(f"no Decision: TRUE/FALSE in the judge reply: {reply[-160:]!r}")
    return found[-1].upper() == "TRUE"


@dataclass
class OfficialJudgeResponse(JudgeResponse):
    """A judge reply that also records the model id the provider reported."""

    model_reported: str | None = None


class OfficialJudge(Judge):
    """``Judge`` that also forwards ``temperature`` and keeps the provider's model string."""

    def __init__(
        self,
        model: str,
        *,
        temperature: float | None = None,
        max_output_tokens: int = 16_000,
        client: Any | None = None,
    ) -> None:
        super().__init__(model, max_output_tokens=max_output_tokens, client=client)
        self.temperature = temperature

    async def complete(  # type: ignore[override]
        self,
        prompt: str,
        *,
        system: str | None = None,
        response_schema: dict | None = None,
    ) -> OfficialJudgeResponse:
        messages = [{"role": "system", "content": system}] if system else []
        messages.append({"role": "user", "content": prompt})
        usage = _ACTIVE_USAGE.get()
        try:
            generation = await self.client.generate(
                messages,
                max_output_tokens=self.max_output_tokens,
                temperature=self.temperature,
                reasoning_effort=self.reasoning_effort,
                response_schema=response_schema,
            )
        except Exception:
            if usage is not None:
                usage.known = False
            raise
        if usage is not None:
            usage.calls += 1
            usage.total_usd += generation.cost_usd or 0.0
            usage.known &= generation.cost_usd is not None
        reported = None
        raw = generation.raw
        if isinstance(raw, dict) and isinstance(raw.get("response"), dict):
            reported = raw["response"].get("model")
        return OfficialJudgeResponse(
            generation.text, generation.usage, generation.cost_usd, model_reported=reported
        )


async def judge_parsed(
    judge: OfficialJudge, prompt: str, parse, spend: JudgeSpend, *, system: str | None, what: str
) -> tuple[Any, OfficialJudgeResponse]:
    """Free-text judge call with ``PARSE_ATTEMPTS`` retries on an unparseable reply."""
    last: ValueError | None = None
    for _ in range(PARSE_ATTEMPTS):
        response = await judge.complete(prompt, system=system)
        spend.add(response)
        try:
            return parse(response.text), response
        except ValueError as error:
            last = error
    raise JudgeOutputError(f"{what}: no parseable judge reply after {PARSE_ATTEMPTS} attempts: {last}")


def label_scores(label: Label) -> dict[str, float]:
    return {
        "score": 1.0 if label == "CORRECT" else 0.0,
        "correct": 1.0 if label == "CORRECT" else 0.0,
        "incorrect": 1.0 if label == "INCORRECT" else 0.0,
        "not_attempted": 1.0 if label == "NOT_ATTEMPTED" else 0.0,
        "attempted": 0.0 if label == "NOT_ATTEMPTED" else 1.0,
    }


def _details(label: str, response: OfficialJudgeResponse, spend: JudgeSpend) -> dict[str, Any]:
    return {
        "label": label,
        "judge_reply": response.text,
        "judge_model_reported": response.model_reported,
        "judge_attempts": spend.calls,
    }


async def grade_simpleqa_verified(
    judge: OfficialJudge, question: str, target: str, predicted: str
) -> Grade:
    """Appendix A prompt, one user message, letter parse."""
    spend = JudgeSpend()
    if is_blank(predicted):
        return spend.grade(label_scores("NOT_ATTEMPTED"), {"label": "NOT_ATTEMPTED", "empty_response": True})
    prompt = SIMPLEQA_VERIFIED_GRADER.format(
        question=question, target=target, predicted_answer=predicted
    )
    label, response = await judge_parsed(
        judge, prompt, parse_letter, spend, system=None, what="simpleqa-verified grader"
    )
    return spend.grade(label_scores(label), _details(label, response, spend))


async def grade_sealqa(judge: OfficialJudge, question: str, target: str, predicted: str) -> Grade:
    """Appendix C / Colab prompt, one user message, letter parse (anchored)."""
    spend = JudgeSpend()
    if is_blank(predicted):
        return spend.grade(label_scores("NOT_ATTEMPTED"), {"label": "NOT_ATTEMPTED", "empty_response": True})
    prompt = SEALQA_GRADER.format(question=question, target=target, predicted_answer=predicted)
    label, response = await judge_parsed(
        judge, prompt, parse_letter, spend, system=None, what="sealqa grader"
    )
    return spend.grade(label_scores(label), _details(label, response, spend))


def frames_scores(correct: bool) -> dict[str, float]:
    return {"score": 1.0 if correct else 0.0}


async def grade_frames(judge: OfficialJudge, question: str, target: str, predicted: str) -> Grade:
    """Figure 6 prompt with the paper's system message; ``Decision:`` TRUE/FALSE."""
    spend = JudgeSpend()
    if is_blank(predicted):
        return spend.grade(frames_scores(False), {"label": "FALSE", "empty_response": True})
    prompt = (
        FRAMES_FIG6_USER.replace("<<question>>", question)
        .replace("<<LLM_response>>", predicted)
        .replace("<<ground_truth_answer>>", target)
    )
    correct, response = await judge_parsed(
        judge, prompt, parse_decision, spend, system=FRAMES_FIG6_SYSTEM, what="frames grader"
    )
    label = "TRUE" if correct else "FALSE"
    return spend.grade(frames_scores(correct), _details(label, response, spend))


def simpleqa_verified_metrics(correct: int, incorrect: int, not_attempted: int) -> dict[str, float]:
    """simple-evals' SimpleQA aggregate: accuracy, accuracy given attempted, F1, attempted share."""
    total = correct + incorrect + not_attempted
    if total == 0:
        return {"accuracy": 0.0, "accuracy_given_attempted": 0.0, "f1": 0.0, "attempted": 0.0, "hedged": 0.0}
    accuracy = correct / total
    attempted = correct + incorrect
    acc_att = correct / attempted if attempted else 0.0
    f1 = 2 * acc_att * accuracy / (acc_att + accuracy) if (acc_att + accuracy) > 0 else 0.0
    return {
        "accuracy": accuracy,
        "accuracy_given_attempted": acc_att,
        "f1": f1,
        "attempted": attempted / total,
        "hedged": not_attempted / total,
    }
