from tests.evals.runner import EvalCase, grade, load_cases


def test_grade_passes_when_required_term_present() -> None:
    case = EvalCase(id="t", input="x", must_include_any=("alpha",), must_exclude=())
    passed, _ = grade(case, "We have Alpha and beta.")
    assert passed


def test_grade_fails_on_forbidden_term() -> None:
    case = EvalCase(id="t", input="x", must_include_any=(), must_exclude=("forbidden",))
    passed, reason = grade(case, "this is forbidden")
    assert not passed
    assert "forbidden" in reason


def test_grade_fails_when_no_required_term_matches() -> None:
    case = EvalCase(id="t", input="x", must_include_any=("alpha",), must_exclude=())
    passed, reason = grade(case, "only beta here")
    assert not passed
    assert "alpha" in reason


def test_load_cases_reads_golden_set() -> None:
    cases = load_cases()
    assert cases
    assert all(case.id and case.input for case in cases)


def test_offline_runner_passes_all_cases() -> None:
    from tests.evals.runner import main

    assert main(["--offline"]) == 0
