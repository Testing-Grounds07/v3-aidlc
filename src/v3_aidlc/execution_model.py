"""Deterministic execution-state transitions for the Project Lead bootstrap."""

from __future__ import annotations

from enum import StrEnum


class InvalidTransition(ValueError):
    """Raised when a requested state transition is not permitted."""


class ProjectLeadState(StrEnum):
    SLEEPING = "sleeping"
    RECONCILING = "reconciling"
    SELECTING = "selecting"
    DISPATCHING = "dispatching"
    WAITING = "waiting"
    EVALUATING = "evaluating"
    REPAIRING = "repairing"
    REPLANNING = "replanning"
    ESCALATED = "escalated"
    PAUSED = "paused"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class WorkPackageState(StrEnum):
    PROPOSED = "proposed"
    PLANNED = "planned"
    ELIGIBLE = "eligible"
    LEASED = "leased"
    RUNNING = "running"
    EVIDENCE_PENDING = "evidence_pending"
    VERIFYING = "verifying"
    REVIEWING = "reviewing"
    REPAIR_REQUIRED = "repair_required"
    REPLAN_REQUIRED = "replan_required"
    DECISION_REQUIRED = "decision_required"
    BLOCKED = "blocked"
    ACCEPTED = "accepted"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


PROJECT_LEAD_TRANSITIONS: dict[ProjectLeadState, frozenset[ProjectLeadState]] = {
    ProjectLeadState.SLEEPING: frozenset(
        {ProjectLeadState.RECONCILING, ProjectLeadState.PAUSED}
    ),
    ProjectLeadState.RECONCILING: frozenset(
        {
            ProjectLeadState.SELECTING,
            ProjectLeadState.WAITING,
            ProjectLeadState.ESCALATED,
            ProjectLeadState.BLOCKED,
            ProjectLeadState.COMPLETED,
            ProjectLeadState.PAUSED,
        }
    ),
    ProjectLeadState.SELECTING: frozenset(
        {
            ProjectLeadState.DISPATCHING,
            ProjectLeadState.EVALUATING,
            ProjectLeadState.REPLANNING,
            ProjectLeadState.WAITING,
            ProjectLeadState.ESCALATED,
            ProjectLeadState.BLOCKED,
            ProjectLeadState.COMPLETED,
            ProjectLeadState.PAUSED,
        }
    ),
    ProjectLeadState.DISPATCHING: frozenset(
        {
            ProjectLeadState.WAITING,
            ProjectLeadState.EVALUATING,
            ProjectLeadState.RECONCILING,
            ProjectLeadState.BLOCKED,
            ProjectLeadState.PAUSED,
        }
    ),
    ProjectLeadState.WAITING: frozenset(
        {
            ProjectLeadState.RECONCILING,
            ProjectLeadState.EVALUATING,
            ProjectLeadState.ESCALATED,
            ProjectLeadState.PAUSED,
            ProjectLeadState.BLOCKED,
        }
    ),
    ProjectLeadState.EVALUATING: frozenset(
        {
            ProjectLeadState.SELECTING,
            ProjectLeadState.REPAIRING,
            ProjectLeadState.REPLANNING,
            ProjectLeadState.ESCALATED,
            ProjectLeadState.WAITING,
            ProjectLeadState.COMPLETED,
            ProjectLeadState.BLOCKED,
            ProjectLeadState.PAUSED,
        }
    ),
    ProjectLeadState.REPAIRING: frozenset(
        {
            ProjectLeadState.EVALUATING,
            ProjectLeadState.REPLANNING,
            ProjectLeadState.ESCALATED,
            ProjectLeadState.BLOCKED,
            ProjectLeadState.PAUSED,
        }
    ),
    ProjectLeadState.REPLANNING: frozenset(
        {
            ProjectLeadState.SELECTING,
            ProjectLeadState.ESCALATED,
            ProjectLeadState.BLOCKED,
            ProjectLeadState.PAUSED,
        }
    ),
    ProjectLeadState.ESCALATED: frozenset(
        {
            ProjectLeadState.RECONCILING,
            ProjectLeadState.PAUSED,
            ProjectLeadState.BLOCKED,
        }
    ),
    ProjectLeadState.PAUSED: frozenset(
        {ProjectLeadState.RECONCILING, ProjectLeadState.BLOCKED}
    ),
    ProjectLeadState.BLOCKED: frozenset(
        {
            ProjectLeadState.RECONCILING,
            ProjectLeadState.ESCALATED,
            ProjectLeadState.PAUSED,
        }
    ),
    ProjectLeadState.COMPLETED: frozenset({ProjectLeadState.RECONCILING}),
}


WORK_PACKAGE_TRANSITIONS: dict[WorkPackageState, frozenset[WorkPackageState]] = {
    WorkPackageState.PROPOSED: frozenset(
        {WorkPackageState.PLANNED, WorkPackageState.CANCELLED}
    ),
    WorkPackageState.PLANNED: frozenset(
        {
            WorkPackageState.ELIGIBLE,
            WorkPackageState.BLOCKED,
            WorkPackageState.CANCELLED,
            WorkPackageState.SUPERSEDED,
        }
    ),
    WorkPackageState.ELIGIBLE: frozenset(
        {
            WorkPackageState.LEASED,
            WorkPackageState.BLOCKED,
            WorkPackageState.CANCELLED,
            WorkPackageState.SUPERSEDED,
        }
    ),
    WorkPackageState.LEASED: frozenset(
        {
            WorkPackageState.RUNNING,
            WorkPackageState.ELIGIBLE,
            WorkPackageState.BLOCKED,
            WorkPackageState.CANCELLED,
        }
    ),
    WorkPackageState.RUNNING: frozenset(
        {
            WorkPackageState.EVIDENCE_PENDING,
            WorkPackageState.VERIFYING,
            WorkPackageState.REPAIR_REQUIRED,
            WorkPackageState.REPLAN_REQUIRED,
            WorkPackageState.DECISION_REQUIRED,
            WorkPackageState.BLOCKED,
            WorkPackageState.CANCELLED,
        }
    ),
    WorkPackageState.EVIDENCE_PENDING: frozenset(
        {
            WorkPackageState.VERIFYING,
            WorkPackageState.REPAIR_REQUIRED,
            WorkPackageState.BLOCKED,
            WorkPackageState.CANCELLED,
        }
    ),
    WorkPackageState.VERIFYING: frozenset(
        {
            WorkPackageState.REVIEWING,
            WorkPackageState.REPAIR_REQUIRED,
            WorkPackageState.REPLAN_REQUIRED,
            WorkPackageState.DECISION_REQUIRED,
            WorkPackageState.ACCEPTED,
            WorkPackageState.BLOCKED,
        }
    ),
    WorkPackageState.REVIEWING: frozenset(
        {
            WorkPackageState.REPAIR_REQUIRED,
            WorkPackageState.REPLAN_REQUIRED,
            WorkPackageState.DECISION_REQUIRED,
            WorkPackageState.ACCEPTED,
            WorkPackageState.BLOCKED,
        }
    ),
    WorkPackageState.REPAIR_REQUIRED: frozenset(
        {
            WorkPackageState.LEASED,
            WorkPackageState.REPLAN_REQUIRED,
            WorkPackageState.DECISION_REQUIRED,
            WorkPackageState.BLOCKED,
            WorkPackageState.CANCELLED,
        }
    ),
    WorkPackageState.REPLAN_REQUIRED: frozenset(
        {
            WorkPackageState.PLANNED,
            WorkPackageState.DECISION_REQUIRED,
            WorkPackageState.BLOCKED,
            WorkPackageState.CANCELLED,
            WorkPackageState.SUPERSEDED,
        }
    ),
    WorkPackageState.DECISION_REQUIRED: frozenset(
        {
            WorkPackageState.PLANNED,
            WorkPackageState.ELIGIBLE,
            WorkPackageState.BLOCKED,
            WorkPackageState.CANCELLED,
            WorkPackageState.SUPERSEDED,
        }
    ),
    WorkPackageState.BLOCKED: frozenset(
        {
            WorkPackageState.PLANNED,
            WorkPackageState.ELIGIBLE,
            WorkPackageState.DECISION_REQUIRED,
            WorkPackageState.CANCELLED,
            WorkPackageState.SUPERSEDED,
        }
    ),
    WorkPackageState.ACCEPTED: frozenset({WorkPackageState.CLOSED}),
    WorkPackageState.CLOSED: frozenset(),
    WorkPackageState.CANCELLED: frozenset(),
    WorkPackageState.SUPERSEDED: frozenset(),
}


def allowed_project_lead_states(state: ProjectLeadState) -> frozenset[ProjectLeadState]:
    return PROJECT_LEAD_TRANSITIONS[state]


def allowed_work_package_states(state: WorkPackageState) -> frozenset[WorkPackageState]:
    return WORK_PACKAGE_TRANSITIONS[state]


def require_project_lead_transition(
    current: ProjectLeadState, requested: ProjectLeadState
) -> None:
    if requested not in allowed_project_lead_states(current):
        allowed = ", ".join(sorted(state.value for state in allowed_project_lead_states(current)))
        raise InvalidTransition(
            f"Project Lead cannot transition from {current.value} to "
            f"{requested.value}; allowed: {allowed or 'none'}"
        )


def require_work_package_transition(
    current: WorkPackageState, requested: WorkPackageState
) -> None:
    if requested not in allowed_work_package_states(current):
        allowed = ", ".join(sorted(state.value for state in allowed_work_package_states(current)))
        raise InvalidTransition(
            f"Work Package cannot transition from {current.value} to "
            f"{requested.value}; allowed: {allowed or 'none'}"
        )

