"""Deciding whether a case can be answered on its own or needs a person.

Two independent reasons send a case to an accountant: the risk level, and
doubtful data. They are separate on purpose — a perfectly low-risk taxpayer
whose invoices do not add up still deserves a human.
"""

from copiloto.analysis import RiskPolicy
from copiloto.graph.state import CopilotState

_ESCALATING_SEVERITIES = frozenset({"warning", "error"})


def make_router(policy: RiskPolicy):
    """Build the routing function for `add_conditional_edges`.

    Returns "ok" or "review", which are the keys of the path map wired in the
    builder. The policy is a value, so switching the escalation contract is a
    configuration change rather than an edit here.
    """

    def route_after_analysis(state: CopilotState) -> str:
        analysis = state.get("analysis")
        if analysis is None:
            # Fail closed. Reaching the router without an analysis means
            # something went wrong upstream, and "we do not know" must never
            # be reported to the taxpayer as "all good".
            return "review"

        if analysis.risk_level in policy.review_levels:
            return "review"

        if any(i.severity in _ESCALATING_SEVERITIES for i in state.get("issues", [])):
            return "review"

        return "ok"

    return route_after_analysis
