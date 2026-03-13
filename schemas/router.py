"""Router output contract converted from router.schema.json."""

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


class VerifyMode(str, Enum):
    LIGHT = "light"
    HARD = "hard"


class AffectState(str, Enum):
    NORMAL = "normal"
    IMPATIENT = "impatient"
    CONFUSED = "confused"
    OVERLOADED = "overloaded"


class RecommendedNextState(str, Enum):
    ANTI_MISLEAD = "T_Anti_Mislead"
    CONCEPT_CLARIFY = "T_Concept_Clarify"
    AFFECT_REPAIR = "T_Affect_Repair"
    ELICIT_WORK = "T_Elicit_Work"
    SCAFFOLD = "T_Scaffold"
    VERIFY = "T_Verify"
    ADVANCE = "T_Step_Advance_When_Ready"
    BAILOUT = "T_Bailout"


class RouterOutput(BaseModel):
    """Strict typed schema + business constraints for router output."""

    model_config = ConfigDict(extra="forbid")

    student_intent: StudentIntent
    step_correctness: StepCorrectness
    mislead_hit: bool
    anti_card_id: str | None
    concept_question: bool
    needs_student_work: bool
    verify_needed: bool
    verify_mode: VerifyMode
    affect_state: AffectState
    recommended_next_state: RecommendedNextState
    confidence: float = Field(ge=0.0, le=1.0)
    missing_prerequisite: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def validate_json_schema_all_of(self) -> "RouterOutput":
        if self.mislead_hit and self.recommended_next_state != RecommendedNextState.ANTI_MISLEAD:
            raise ValueError("recommended_next_state must be T_Anti_Mislead when mislead_hit is true")

        if self.concept_question and self.recommended_next_state != RecommendedNextState.CONCEPT_CLARIFY:
            raise ValueError("recommended_next_state must be T_Concept_Clarify when concept_question is true")

        if self.needs_student_work and self.recommended_next_state != RecommendedNextState.ELICIT_WORK:
            raise ValueError("recommended_next_state must be T_Elicit_Work when needs_student_work is true")

        if self.step_correctness == StepCorrectness.CORRECT and self.verify_needed:
            if self.recommended_next_state != RecommendedNextState.VERIFY:
                raise ValueError("recommended_next_state must be T_Verify when step is correct and verify_needed is true")

        if self.step_correctness == StepCorrectness.CORRECT and not self.verify_needed:
            if self.recommended_next_state != RecommendedNextState.ADVANCE:
                raise ValueError(
                    "recommended_next_state must be T_Step_Advance_When_Ready when step is correct and verify_needed is false"
                )

        if self.mislead_hit and not self.anti_card_id:
            raise ValueError("anti_card_id must be provided when mislead_hit is true")

        return self
