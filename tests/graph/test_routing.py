"""Routing: when does a case stop being self-service.

The contract chosen for this project is the literal reading of the request:
"risk or doubtful data goes to an accountant". The policy is a value, so the
tests exercise both readings and neither is hard-coded into the router.
"""

from decimal import Decimal

import pytest

from copiloto.analysis import Analysis, RiskPolicy
from copiloto.graph.routing import make_router
from copiloto.graph.state import CopilotState
from copiloto.models import Issue

DEFAULT = RiskPolicy()
LENIENT = RiskPolicy(review_levels=frozenset({"high", "exclusion"}))


def analysis(level: str) -> Analysis:
    return Analysis(
        accumulated_12m=Decimal("9600000"),
        projected_12m=Decimal("9733333.33"),
        computed_category="A",
        registered_category="A",
        risk_level=level,  # pyright: ignore[reportArgumentType]
        reasons=(),
        headroom_registered=Decimal("2409410.45"),
        headroom_top=Decimal("117010838.75"),
        months_to_registered_cap=Decimal("3.0"),
        months_to_top_cap=Decimal("144.3"),
    )


def route(level: str, issues=(), policy: RiskPolicy = DEFAULT) -> str:
    state: CopilotState = {"analysis": analysis(level), "issues": list(issues)}
    return make_router(policy)(state)


def issue(severity: str) -> Issue:
    return Issue(code="X", severity=severity, message="m")  # pyright: ignore[reportArgumentType]


class TestRiskLevelRouting:
    def test_low_risk_goes_straight_to_the_report(self) -> None:
        assert route("low") == "ok"

    @pytest.mark.parametrize("level", ["medium", "high", "exclusion"])
    def test_every_other_level_goes_to_an_accountant(self, level: str) -> None:
        assert route(level) == "review"


class TestPolicyIsAValueNotAHardCodedRule:
    def test_the_lenient_policy_lets_medium_reach_the_report(self) -> None:
        """Changing the contract is one line in RiskPolicy, not a code change."""
        assert route("medium", policy=LENIENT) == "ok"

    @pytest.mark.parametrize("level", ["high", "exclusion"])
    def test_the_lenient_policy_still_escalates_the_serious_levels(self, level: str) -> None:
        assert route(level, policy=LENIENT) == "review"


class TestDoubtfulData:
    @pytest.mark.parametrize("severity", ["warning", "error"])
    def test_a_doubtful_invoice_escalates_even_at_low_risk(self, severity: str) -> None:
        """"Doubtful data" is a separate reason to escalate, independent of risk."""
        assert route("low", issues=(issue(severity),)) == "review"

    def test_informational_issues_do_not_escalate(self) -> None:
        """An invoice outside the window is normal, not a problem."""
        assert route("low", issues=(issue("info"),)) == "ok"

    def test_a_doubtful_invoice_escalates_under_the_lenient_policy_too(self) -> None:
        assert route("low", issues=(issue("warning"),), policy=LENIENT) == "review"

    def test_mixed_issues_escalate_if_any_one_of_them_is_serious(self) -> None:
        assert route("low", issues=(issue("info"), issue("warning"))) == "review"


class TestMissingAnalysis:
    def test_a_case_without_analysis_is_escalated_not_approved(self) -> None:
        """Failing closed: if we do not know, a person decides."""
        state: CopilotState = {"issues": []}

        assert make_router(DEFAULT)(state) == "review"
