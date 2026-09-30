"""D-134: the evaluation set's template and how a finished run is read back."""

from autora.domains.newsroom.evaluation import EVAL_TEMPLATE, CaseResult, summarize
from autora.domains.newsroom.workflow import TEMPLATE


def test_the_set_runs_the_production_loops_from_the_draft_on():
    assert [n.name for n in EVAL_TEMPLATE.nodes] == ["analysis", "draft", "review", "chief_review"]
    production = {
        (loop.check, loop.back_to, loop.max_rounds)
        for loop in TEMPLATE.loops
        if loop.check != "approve"
    }
    assert {
        (loop.check, loop.back_to, loop.max_rounds) for loop in EVAL_TEMPLATE.loops
    } == production
    assert EVAL_TEMPLATE.halts == TEMPLATE.halts
    # nothing a person decides, nothing published
    assert not {"approve", "publish", "distribute"} & {n.name for n in EVAL_TEMPLATE.nodes}


def test_summarize_reads_the_set_as_shares_rounds_and_what_was_raised():
    results = [
        CaseResult("a", "A", "PUBLISHED", first_review="accept", drafts=1, reviews=1,
                   ended="accepted", cost_usd=0.02, seconds=60),
        CaseResult("b", "B", "REJECTED", first_review="revise", drafts=3, reviews=3, sent_back=2,
                   ended="rejected", issue_kinds={"missing_context": 3, "fact": 1},
                   cost_usd=0.06, seconds=180),
        CaseResult("c", "C", "PUBLISHED", first_review="revise", drafts=2, reviews=2, sent_back=1,
                   ended="accepted", issue_kinds={"missing_context": 1}, cost_usd=0.04),
    ]  # fmt: skip
    s = summarize(results)
    assert s["stories"] == 3
    assert round(s["first_review_accepted"], 2) == 0.33
    assert round(s["accepted"], 2) == 0.67 and round(s["rejected"], 2) == 0.33
    assert s["drafts_per_story"] == 2
    assert round(s["cost_per_story_usd"], 2) == 0.04
    assert s["seconds_per_story"] == 120
    assert list(s["issue_kinds"]) == ["missing_context", "fact"]
