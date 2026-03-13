"""LangGraph implementation of Step-FSM using router conditional transitions."""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from schemas.context import SharedContext
from schemas.router import RecommendedNextState, RouterOutput


class StepGraphState(TypedDict, total=False):
    context: SharedContext
    router_output: RouterOutput
    emitted_event: str


def node_probe_new_step(state: StepGraphState) -> StepGraphState:
    return state


def node_probe_retry(state: StepGraphState) -> StepGraphState:
    return state


def node_probe_recovery(state: StepGraphState) -> StepGraphState:
    return state


def node_router(state: StepGraphState) -> StepGraphState:
    """Placeholder router hook. Inject RouterOutput before invoking graph."""
    if "router_output" not in state:
        raise ValueError("router_output is required before entering T_Router")
    return state


def node_anti_mislead(state: StepGraphState) -> StepGraphState:
    return {**state, "emitted_event": "EVT_RECOVERY_READY"}


def node_concept_clarify(state: StepGraphState) -> StepGraphState:
    return {**state, "emitted_event": "EVT_CLARIFIED"}


def node_affect_repair(state: StepGraphState) -> StepGraphState:
    return {**state, "emitted_event": "EVT_REFOCUSED"}


def node_elicit_work(state: StepGraphState) -> StepGraphState:
    return state


def node_scaffold(state: StepGraphState) -> StepGraphState:
    return state


def node_verify(state: StepGraphState) -> StepGraphState:
    return state


def node_step_advance_when_ready(state: StepGraphState) -> StepGraphState:
    return {**state, "emitted_event": "EVT_ADVANCE_STEP"}


def node_bailout(state: StepGraphState) -> StepGraphState:
    return {**state, "emitted_event": "EVT_DIRECT_DONE"}


def route_from_router(state: StepGraphState) -> str:
    router_output = state["router_output"]
    next_state = router_output.recommended_next_state

    mapping = {
        RecommendedNextState.ANTI_MISLEAD: "T_Anti_Mislead",
        RecommendedNextState.CONCEPT_CLARIFY: "T_Concept_Clarify",
        RecommendedNextState.AFFECT_REPAIR: "T_Affect_Repair",
        RecommendedNextState.ELICIT_WORK: "T_Elicit_Work",
        RecommendedNextState.SCAFFOLD: "T_Scaffold",
        RecommendedNextState.VERIFY: "T_Verify",
        RecommendedNextState.ADVANCE: "T_Step_Advance_When_Ready",
        RecommendedNextState.BAILOUT: "T_Bailout",
    }
    return mapping[next_state]


def build_step_graph():
    graph = StateGraph(StepGraphState)

    graph.add_node("T_Probe_NewStep", node_probe_new_step)
    graph.add_node("T_Probe_Retry", node_probe_retry)
    graph.add_node("T_Probe_Recovery", node_probe_recovery)
    graph.add_node("T_Router", node_router)
    graph.add_node("T_Anti_Mislead", node_anti_mislead)
    graph.add_node("T_Concept_Clarify", node_concept_clarify)
    graph.add_node("T_Affect_Repair", node_affect_repair)
    graph.add_node("T_Elicit_Work", node_elicit_work)
    graph.add_node("T_Scaffold", node_scaffold)
    graph.add_node("T_Verify", node_verify)
    graph.add_node("T_Step_Advance_When_Ready", node_step_advance_when_ready)
    graph.add_node("T_Bailout", node_bailout)

    graph.add_edge(START, "T_Probe_NewStep")
    graph.add_edge("T_Probe_NewStep", "T_Router")
    graph.add_edge("T_Probe_Retry", "T_Router")
    graph.add_edge("T_Probe_Recovery", "T_Router")
    graph.add_edge("T_Elicit_Work", "T_Router")
    graph.add_edge("T_Scaffold", "T_Router")

    graph.add_conditional_edges(
        "T_Router",
        route_from_router,
        {
            "T_Anti_Mislead": "T_Anti_Mislead",
            "T_Concept_Clarify": "T_Concept_Clarify",
            "T_Affect_Repair": "T_Affect_Repair",
            "T_Elicit_Work": "T_Elicit_Work",
            "T_Scaffold": "T_Scaffold",
            "T_Verify": "T_Verify",
            "T_Step_Advance_When_Ready": "T_Step_Advance_When_Ready",
            "T_Bailout": "T_Bailout",
        },
    )

    graph.add_edge("T_Anti_Mislead", "T_Probe_Recovery")
    graph.add_edge("T_Concept_Clarify", "T_Probe_Retry")
    graph.add_edge("T_Affect_Repair", "T_Scaffold")
    graph.add_edge("T_Verify", "T_Scaffold")
    graph.add_edge("T_Bailout", "T_Verify")
    graph.add_edge("T_Step_Advance_When_Ready", END)

    return graph.compile()
