"""Shared tutoring context models derived from tutoring_v6.yaml."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StudentIntent(str, Enum):
    SOLVE_ATTEMPT = "solve_attempt"
    CONCEPT_QUESTION = "concept_question"
    GIVE_UP = "give_up"
    FAST_GUESS = "fast_guess"
    REFLECTION = "reflection"


class StepCorrectness(str, Enum):
    WRONG = "wrong"
    PARTIAL_CORRECT = "partial_correct"
    CORRECT_BUT_INCOMPLETE = "correct_but_incomplete"
    CORRECT = "correct"


class AffectState(str, Enum):
    NORMAL = "normal"
    IMPATIENT = "impatient"
    CONFUSED = "confused"
    OVERLOADED = "overloaded"


class VerifyMode(str, Enum):
    LIGHT = "light"
    HARD = "hard"


class StepStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    SKIPPED = "skipped"


class SessionContext(BaseModel):
    """Session-level runtime context."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    student_id: str
    teacher_mode: bool = False
    session_state: str
    current_problem_id: str | None = None
    current_goal: str | None = None
    current_recommendations: list[str] = Field(default_factory=list)


class ProblemContext(BaseModel):
    """Problem-level runtime context."""

    model_config = ConfigDict(extra="forbid")

    problem_state: str
    solution_id: str | None = None
    current_branch_id: str | None = None
    current_step_id: str | None = None
    current_step_order: int = 0
    has_next_step: bool = False
    candidate_branches: list[str] = Field(default_factory=list)
    problem_done: bool = False

    @model_validator(mode="after")
    def validate_step_order(self) -> "ProblemContext":
        if self.current_step_order < 0:
            raise ValueError("current_step_order must be >= 0")
        return self


class StepContext(BaseModel):
    """Step-level tutoring context for the Step-FSM."""

    model_config = ConfigDict(extra="forbid")

    step_state: str
    step_goal: str | None = None
    step_status: StepStatus = StepStatus.NOT_STARTED
    hint_level: int = 0
    attempt_count: int = 0
    max_attempts_per_step: int = 3
    student_last_reply: str = ""
    assistant_last_reply: str = ""
    student_intent: StudentIntent | None = None
    step_correctness: StepCorrectness | None = None
    mislead_hit: bool = False
    anti_card_id: str | None = None
    concept_question: bool = False
    needs_student_work: bool = False
    verify_needed: bool = False
    verify_mode: VerifyMode = VerifyMode.LIGHT
    affect_state: AffectState = AffectState.NORMAL
    recommended_next_state: str | None = None
    confidence: float = 0.0

    @model_validator(mode="after")
    def validate_bounds(self) -> "StepContext":
        if self.hint_level < 0:
            raise ValueError("hint_level must be >= 0")
        if self.attempt_count < 0:
            raise ValueError("attempt_count must be >= 0")
        if self.max_attempts_per_step <= 0:
            raise ValueError("max_attempts_per_step must be > 0")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if self.mislead_hit and not self.anti_card_id:
            raise ValueError("anti_card_id is required when mislead_hit is true")
        return self


class SharedContext(BaseModel):
    """V6 shared context root for Session/Problem/Step layers."""

    model_config = ConfigDict(extra="forbid")

    session: SessionContext
    problem: ProblemContext
    step: StepContext
