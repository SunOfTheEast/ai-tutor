## 1) `tutoring_v6.yaml`
YAML
version: "1.0.0"
machine_name: "tutoring_v6"
description: >
  Hierarchical FSM for AI tutoring.
  Session-FSM -> Problem-FSM -> Step-FSM.
  V1-V5 capabilities are nested as sub-policies inside V6.

naming_conventions:
  session_states_prefix: "S_"
  problem_states_prefix: "P_"
  step_states_prefix: "T_"
  events_prefix: "EVT_"

feature_flags:
  step_kernel:
    enable_probe_retry: true
    enable_probe_recovery: true
    enable_elicit_work: true
  rescue_layer:
    enable_anti_mislead: true
    enable_concept_clarify: true
    enable_affect_repair: true
    enable_bailout: true
  verify_layer:
    enable_verify_light: true
    enable_verify_hard: true
  branch_layer:
    enable_branch_select: true
    enable_branch_switch: true
  session_layer:
    enable_reflection: true
    enable_recommendation: true
    enable_learner_state_update: false

enums:
  student_intent:
    - solve_attempt
    - concept_question
    - give_up
    - fast_guess
    - reflection
  step_correctness:
    - wrong
    - partial_correct
    - correct_but_incomplete
    - correct
  affect_state:
    - normal
    - impatient
    - confused
    - overloaded
  card_role:
    - primary_method
    - secondary_method
    - anti_mislead
    - verify
    - pedagogy
  bailout_mode:
    - direct_explain
    - rollback
    - mark_and_move
  verify_mode:
    - light
    - hard

shared_context:
  session:
    session_id: "string"
    student_id: "string"
    teacher_mode: false
    session_state: "string"
    current_problem_id: "string|null"
    current_goal: "string|null"
    current_recommendations: []
  problem:
    problem_state: "string"
    solution_id: "string|null"
    current_branch_id: "string|null"
    current_step_id: "string|null"
    current_step_order: 0
    has_next_step: false
    candidate_branches: []
    problem_done: false
  step:
    step_state: "string"
    step_goal: "string|null"
    step_status: "not_started"
    hint_level: 0
    attempt_count: 0
    max_attempts_per_step: 3
    student_last_reply: ""
    assistant_last_reply: ""
    student_intent: null
    step_correctness: null
    mislead_hit: false
    anti_card_id: null
    concept_question: false
    needs_student_work: false
    verify_needed: false
    verify_mode: "light"
    affect_state: "normal"
    recommended_next_state: null
    confidence: 0.0
  cards:
    method_card_ids: []
    anti_card_ids: []
    verify_card_ids: []
    cards_loaded: []
  runtime:
    trace_log_ids: []
    last_event: null
    snapshot_version: 0

side_effects:
  on_every_transition:
    - append_trace_log
    - persist_session_snapshot
  on_problem_close:
    - build_problem_postmortem
    - build_learning_signals
  on_session_end:
    - persist_recommendations
    - update_learner_state_if_enabled

contracts:
  outputs:
    question_only:
      must:
        - "end_with_question"
      must_not:
        - "full_solution"
        - "next_step_spoiler"
        - "multiple_questions"
    constrained_explanation:
      must:
        - "why_tempting"
        - "why_wrong"
        - "recovery_bridge"
      must_not:
        - "full_solution"
        - "next_step_spoiler"
    local_clarification_only:
      must:
        - "explain_current_step_only"
        - "return_to_current_step"
      must_not:
        - "full_problem_explanation"
        - "next_step_spoiler"
    ask_for_local_action:
      must:
        - "request_single_local_formula_or_action"
      must_not:
        - "solve_entire_problem"
    one_step_check:
      must:
        - "check_current_step_only"
      must_not:
        - "new_chapter_explanation"
    summary_plus_transition:
      must:
        - "summarize_current_step_core_action"
        - "transition_to_next_step_or_problem_recap"
      must_not:
        - "repeat_whole_solution"
    current_step_direct_only:
      must:
        - "explain_current_step_only"
      must_not:
        - "full_solution"

session_fsm:
  initial_state: "S_Session_Start"
  states:
    S_Session_Start:
      kind: visible
      description: "User enters tutoring session."
      on:
        EVT_SESSION_INIT:
          target: "S_Goal_Setting"

    S_Goal_Setting:
      kind: visible
      description: "Select goal, mode, or target problem."
      on:
        EVT_GOAL_CONFIRMED:
          target: "S_Problem_Loading"

    S_Problem_Loading:
      kind: background
      description: "Load problem, solution, steps, cards, caches."
      entry_actions:
        - load_problem
        - load_solution
        - init_problem_fsm
      on:
        EVT_PROBLEM_READY:
          target: "S_Tutoring"
        EVT_LOAD_FAILED:
          target: "S_Session_End"

    S_Tutoring:
      kind: visible
      description: "Main tutoring phase. Delegates to Problem-FSM."
      invokes: "problem_fsm"
      on:
        EVT_PROBLEM_DONE:
          target: "S_Reflection"
        EVT_SESSION_PAUSE:
          target: "S_Session_Suspend"

    S_Reflection:
      kind: visible
      description: "Reflect on completed problem."
      enabled_if: "feature_flags.session_layer.enable_reflection"
      entry_actions:
        - summarize_problem_trace
        - generate_reflection
      on:
        EVT_REFLECTION_DONE:
          target: "S_Recommendation"

    S_Recommendation:
      kind: visible
      description: "Recommend next problems/cards."
      enabled_if: "feature_flags.session_layer.enable_recommendation"
      entry_actions:
        - fetch_related_problems
        - fetch_related_cards
      on:
        EVT_NEXT_PROBLEM:
          target: "S_Problem_Loading"
        EVT_FINISH_SESSION:
          target: "S_Session_End"

    S_Session_Suspend:
      kind: background
      description: "Persist snapshot and wait for resume."
      entry_actions:
        - persist_snapshot
      on:
        EVT_RESUME:
          target: "S_Tutoring"
        EVT_ABORT:
          target: "S_Session_End"

    S_Session_End:
      kind: terminal
      description: "End session and persist final artifacts."

problem_fsm:
  initial_state: "P_Problem_Initialized"
  states:
    P_Problem_Initialized:
      kind: background
      on:
        EVT_PROBLEM_LOADED:
          target: "P_Problem_Preprocess"

    P_Problem_Preprocess:
      kind: background
      description: "Split steps, tag steps, attach cards."
      entry_actions:
        - split_solution_steps
        - tag_solution_steps
        - link_cards_to_steps
      on:
        EVT_STEPS_READY:
          target: "P_Strategy_Build"
        EVT_PREPROCESS_FAILED:
          target: "P_Problem_Abort"

    P_Strategy_Build:
      kind: background
      description: "Build solution graph and branch metadata."
      entry_actions:
        - build_solution_graph
        - detect_candidate_branches
        - mark_verify_risk_steps
      on:
        EVT_STRATEGY_READY:
          target: "P_Step_Enter"

    P_Step_Enter:
      kind: background
      description: "Prepare current step context and choose initial step state."
      entry_actions:
        - load_current_step_context
        - reset_hint_level_if_new_step
        - reset_attempt_count_if_new_step
      on:
        EVT_STEP_CONTEXT_READY:
          target: "P_Step_Tutor"

    P_Step_Tutor:
      kind: visible
      description: "Delegate current step tutoring to Step-FSM."
      invokes: "step_fsm"
      on:
        EVT_ADVANCE_STEP:
          target: "P_Step_Enter"
        EVT_ROLLBACK_STEP:
          target: "P_Step_Enter"
        EVT_BRANCH_PROPOSED:
          target: "P_Branch_Select"
        EVT_PROBLEM_COMPLETE:
          target: "P_Problem_Recap"
        EVT_ABORT_PROBLEM:
          target: "P_Problem_Abort"

    P_Branch_Select:
      kind: background
      description: "Select or switch to a valid solution branch."
      enabled_if: "feature_flags.branch_layer.enable_branch_switch"
      entry_actions:
        - evaluate_candidate_branches
        - select_branch
      on:
        EVT_BRANCH_CONFIRMED:
          target: "P_Step_Enter"
        EVT_BRANCH_REJECTED:
          target: "P_Step_Tutor"

    P_Problem_Recap:
      kind: visible
      description: "Summarize whole problem."
      entry_actions:
        - generate_problem_recap
        - generate_misconception_summary
      on:
        EVT_RECAP_DONE:
          target: "P_Problem_Close"

    P_Problem_Close:
      kind: terminal
      description: "Problem finished."

    P_Problem_Abort:
      kind: terminal
      description: "Problem aborted."

step_fsm:
  initial_state: "T_Probe_NewStep"
  states:
    T_Probe_NewStep:
      kind: visible
      output_contract: "question_only"
      description: "First probe for a new step."
      on:
        EVT_STUDENT_REPLY:
          target: "T_Router"

    T_Probe_Retry:
      kind: visible
      enabled_if: "feature_flags.step_kernel.enable_probe_retry"
      output_contract: "question_only"
      description: "Probe after failed attempt on same step."
      on:
        EVT_STUDENT_REPLY:
          target: "T_Router"

    T_Probe_Recovery:
      kind: visible
      enabled_if: "feature_flags.step_kernel.enable_probe_recovery"
      output_contract: "question_only"
      description: "Probe after anti-mislead recovery."
      on:
        EVT_STUDENT_REPLY:
          target: "T_Router"

    T_Router:
      kind: background
      description: "Structured diagnosis and next-state selection."
      entry_actions:
        - run_router_classifier
      on:
        EVT_ROUTED_MISLEAD:
          target: "T_Anti_Mislead"
        EVT_ROUTED_CONCEPT:
          target: "T_Concept_Clarify"
        EVT_ROUTED_AFFECT:
          target: "T_Affect_Repair"
        EVT_ROUTED_ELICIT:
          target: "T_Elicit_Work"
        EVT_ROUTED_VERIFY:
          target: "T_Verify"
        EVT_ROUTED_ADVANCE:
          target: "T_Step_Advance_When_Ready"
        EVT_ROUTED_BAILOUT:
          target: "T_Bailout"
        EVT_ROUTED_DEFAULT:
          target: "T_Scaffold"

    T_Anti_Mislead:
      kind: visible
      enabled_if: "feature_flags.rescue_layer.enable_anti_mislead"
      output_contract: "constrained_explanation"
      description: "Explain tempting wrong path and return to mainline."
      on:
        EVT_RECOVERY_READY:
          target: "T_Probe_Recovery"

    T_Concept_Clarify:
      kind: visible
      enabled_if: "feature_flags.rescue_layer.enable_concept_clarify"
      output_contract: "local_clarification_only"
      description: "Clarify why current step uses this move."
      on:
        EVT_CLARIFIED:
          target: "T_Probe_Retry"

    T_Affect_Repair:
      kind: visible
      enabled_if: "feature_flags.rescue_layer.enable_affect_repair"
      output_contract: "local_clarification_only"
      description: "Reduce cognitive load and repair pacing."
      on:
        EVT_REFOCUSED:
          target: "T_Scaffold"
        EVT_OVERLOADED:
          target: "T_Bailout"

    T_Elicit_Work:
      kind: visible
      enabled_if: "feature_flags.step_kernel.enable_elicit_work"
      output_contract: "ask_for_local_action"
      description: "Ask student to produce the local formula/action."
      on:
        EVT_STUDENT_REPLY:
          target: "T_Router"

    T_Scaffold:
      kind: visible
      output_contract: "local_clarification_only"
      description: "Run hint ladder from L0 to L3."
      sub_states:
        T_Scaffold_L0:
          description: "Mirror / observation."
        T_Scaffold_L1:
          description: "Direction hint."
        T_Scaffold_L2:
          description: "Critical local step."
        T_Scaffold_L3:
          description: "Direct current-step explanation."
      on:
        EVT_STUDENT_REPLY:
          target: "T_Router"
        EVT_HINT_EXHAUSTED:
          target: "T_Bailout"

    T_Verify:
      kind: visible
      description: "Verify current-step understanding."
      enabled_if: "feature_flags.verify_layer.enable_verify_light"
      output_contract: "one_step_check"
      sub_states:
        T_Verify_Light:
          description: "Simple one-step verification."
        T_Verify_Hard:
          description: "Hard verification for suspected fake mastery."
      on:
        EVT_VERIFY_PASS:
          target: "T_Step_Advance_When_Ready"
        EVT_VERIFY_FAIL:
          target: "T_Scaffold"

    T_Step_Advance_When_Ready:
      kind: visible
      output_contract: "summary_plus_transition"
      description: "Summarize current step and advance."
      on:
        EVT_HAS_NEXT_STEP:
          target: "__RETURN_EVT_ADVANCE_STEP__"
        EVT_NO_NEXT_STEP:
          target: "__RETURN_EVT_PROBLEM_COMPLETE__"

    T_Bailout:
      kind: visible
      enabled_if: "feature_flags.rescue_layer.enable_bailout"
      description: "Protect pacing and prevent step deadlock."
      sub_states:
        T_Bailout_DirectExplain:
          output_contract: "current_step_direct_only"
          description: "Directly explain current step only."
        T_Bailout_Rollback:
          description: "Rollback to previous step for missing prerequisite."
        T_Bailout_MarkAndMove:
          description: "Mark weak mastery and continue."
      on:
        EVT_DIRECT_DONE:
          target: "T_Verify"
        EVT_ROLLBACK_REQUEST:
          target: "__RETURN_EVT_ROLLBACK_STEP__"
        EVT_MARK_AND_MOVE:
          target: "T_Step_Advance_When_Ready"

guards:
  router_to_mislead: "mislead_hit == true"
  router_to_concept: "student_intent == 'concept_question' or concept_question == true"
  router_to_affect: "affect_state in ['impatient', 'confused', 'overloaded']"
  router_to_elicit: "step_correctness == 'correct_but_incomplete' or needs_student_work == true"
  router_to_verify: "step_correctness == 'correct' and verify_needed == true"
  router_to_advance: "step_correctness == 'correct' and verify_needed == false"
  router_to_bailout: "attempt_count >= max_attempts_per_step or affect_state == 'overloaded'"

runtime_policies:
  hint_ladder:
    initial_level: 0
    max_level: 3
    increment_on:
      - EVT_ROUTED_DEFAULT
      - EVT_VERIFY_FAIL
  verify_policy:
    light_if:
      - "verify_needed == true"
      - "student_intent != 'fast_guess'"
    hard_if:
      - "student_intent == 'fast_guess'"
      - "confidence < 0.6"
      - "student_reply in ['懂了', '会了', '就是这样']"
  bailout_policy:
    choose_direct_explain_if:
      - "attempt_count >= max_attempts_per_step"
      - "step_goal is still locally teachable"
    choose_rollback_if:
      - "missing_prerequisite == true"
    choose_mark_and_move_if:
      - "session_pacing_priority == true"

logging:
  trace_fields:
    - session_id
    - problem_id
    - step_id
    - turn_index
    - from_state
    - to_state
    - student_reply
    - assistant_reply
    - router_output
    - hint_level
    - verify_mode
    - bailout_mode
    - mislead_hit
    - confidence

return_events_from_step_fsm:
  - EVT_ADVANCE_STEP
  - EVT_ROLLBACK_STEP
  - EVT_BRANCH_PROPOSED
  - EVT_PROBLEM_COMPLETE
  - EVT_ABORT_PROBLEM

---

## 2) `router.schema.json`
JSON
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/router.schema.json",
  "title": "Tutor Router Output Schema",
  "type": "object",
  "additionalProperties": false,
  "required": [
"student_intent",
"step_correctness",
"mislead_hit",
"anti_card_id",
"concept_question",
"needs_student_work",
"verify_needed",
"verify_mode",
"affect_state",
"recommended_next_state",
"confidence"
  ],
  "properties": {
    "student_intent": {
      "type": "string",
      "enum": [
"solve_attempt",
"concept_question",
"give_up",
"fast_guess",
"reflection"
      ]
    },
    "step_correctness": {
      "type": "string",
      "enum": [
"wrong",
"partial_correct",
"correct_but_incomplete",
"correct"
      ]
    },
    "mislead_hit": {
      "type": "boolean"
    },
    "anti_card_id": {
      "type": ["string", "null"],
      "description": "Matched anti-mislead card id if mislead_hit is true."
    },
    "concept_question": {
      "type": "boolean"
    },
    "needs_student_work": {
      "type": "boolean",
      "description": "True if student has right direction but must write local formula/action."
    },
    "verify_needed": {
      "type": "boolean"
    },
    "verify_mode": {
      "type": "string",
      "enum": ["light", "hard"]
    },
    "affect_state": {
      "type": "string",
      "enum": [
"normal",
"impatient",
"confused",
"overloaded"
      ]
    },
    "recommended_next_state": {
      "type": "string",
      "enum": [
"T_Anti_Mislead",
"T_Concept_Clarify",
"T_Affect_Repair",
"T_Elicit_Work",
"T_Scaffold",
"T_Verify",
"T_Step_Advance_When_Ready",
"T_Bailout"
      ]
    },
    "confidence": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0
    },
    "missing_prerequisite": {
      "type": "boolean",
      "default": false
    },
    "notes": {
      "type": "string"
    }
  },
  "allOf": [
    {
      "if": {
        "properties": { "mislead_hit": { "const": true } },
        "required": ["mislead_hit"]
      },
      "then": {
        "properties": {
          "recommended_next_state": { "const": "T_Anti_Mislead" }
        }
      }
    },
    {
      "if": {
        "properties": { "concept_question": { "const": true } },
        "required": ["concept_question"]
      },
      "then": {
        "properties": {
          "recommended_next_state": { "const": "T_Concept_Clarify" }
        }
      }
    },
    {
      "if": {
        "properties": { "needs_student_work": { "const": true } },
        "required": ["needs_student_work"]
      },
      "then": {
        "properties": {
          "recommended_next_state": { "const": "T_Elicit_Work" }
        }
      }
    },
    {
      "if": {
        "properties": {
          "step_correctness": { "const": "correct" },
          "verify_needed": { "const": true }
        },
        "required": ["step_correctness", "verify_needed"]
      },
      "then": {
        "properties": {
          "recommended_next_state": { "const": "T_Verify" }
        }
      }
    },
    {
      "if": {
        "properties": {
          "step_correctness": { "const": "correct" },
          "verify_needed": { "const": false }
        },
        "required": ["step_correctness", "verify_needed"]
      },
      "then": {
        "properties": {
          "recommended_next_state": { "const": "T_Step_Advance_When_Ready" }
        }
      }
    }
  ]
}

---

## 3) `fsm_events.yaml`
YAML
version: "1.0.0"
title: "Parent-Child FSM Event Table"

event_types:
  upward_events:
    description: "Events emitted from child FSM to parent FSM."
  downward_events:
    description: "Commands or setup signals emitted from parent FSM to child FSM."
  local_events:
    description: "Events consumed within the same FSM."

session_to_problem:
  downward_events:
    - event: EVT_PROBLEM_READY
      from: S_Problem_Loading
      to: P_Problem_Initialized
      meaning: "Problem assets loaded; initialize Problem-FSM."
    - event: EVT_SESSION_PAUSE
      from: S_Tutoring
      to: P_ANY
      meaning: "Pause tutoring and persist snapshots."
  upward_events:
    - event: EVT_PROBLEM_DONE
      from: P_Problem_Close
      to: S_Tutoring
      meaning: "Current problem finished; Session-FSM may enter Reflection."
    - event: EVT_ABORT_PROBLEM
      from: P_Problem_Abort
      to: S_Tutoring
      meaning: "Problem aborted; Session-FSM decides next action."

problem_to_step:
  downward_events:
    - event: EVT_STEP_CONTEXT_READY
      from: P_Step_Enter
      to: T_Probe_NewStep
      meaning: "Current step context loaded; start Step-FSM."
    - event: EVT_STEP_RETRY
      from: P_Step_Enter
      to: T_Probe_Retry
      meaning: "Re-enter same step after retry."
    - event: EVT_STEP_RECOVERY
      from: P_Step_Enter
      to: T_Probe_Recovery
      meaning: "Re-enter current step after anti-mislead recovery."
  upward_events:
    - event: EVT_ADVANCE_STEP
      from: T_Step_Advance_When_Ready
      to: P_Step_Tutor
      meaning: "Current step passed; advance to next step."
    - event: EVT_ROLLBACK_STEP
      from: T_Bailout_Rollback
      to: P_Step_Tutor
      meaning: "Rollback to previous step."
    - event: EVT_BRANCH_PROPOSED
      from: T_Router
      to: P_Step_Tutor
      meaning: "Alternative valid branch detected; Problem-FSM may switch branches."
    - event: EVT_PROBLEM_COMPLETE
      from: T_Step_Advance_When_Ready
      to: P_Step_Tutor
      meaning: "No next step; whole problem completed."
    - event: EVT_ABORT_PROBLEM
      from: T_Bailout
      to: P_Step_Tutor
      meaning: "Abort current problem."

step_local_events:
  - event: EVT_STUDENT_REPLY
    from: T_Probe_NewStep|T_Probe_Retry|T_Probe_Recovery|T_Elicit_Work|T_Scaffold
    to: T_Router
    meaning: "Student responds; route next action."

  - event: EVT_ROUTED_MISLEAD
    from: T_Router
    to: T_Anti_Mislead
    meaning: "Wrong but tempting method detected."

  - event: EVT_ROUTED_CONCEPT
    from: T_Router
    to: T_Concept_Clarify
    meaning: "Student asks conceptual why-question."

  - event: EVT_ROUTED_AFFECT
    from: T_Router
    to: T_Affect_Repair
    meaning: "Student shows overload/impatience/confusion."

  - event: EVT_ROUTED_ELICIT
    from: T_Router
    to: T_Elicit_Work
    meaning: "Student direction is acceptable but must produce local formula/action."

  - event: EVT_ROUTED_VERIFY
    from: T_Router
    to: T_Verify
    meaning: "Student appears correct; verify before advance."

  - event: EVT_ROUTED_ADVANCE
    from: T_Router
    to: T_Step_Advance_When_Ready
    meaning: "Student step is sufficiently correct; may advance."

  - event: EVT_ROUTED_BAILOUT
    from: T_Router
    to: T_Bailout
    meaning: "Too many failures or overloaded affect state."

  - event: EVT_ROUTED_DEFAULT
    from: T_Router
    to: T_Scaffold
    meaning: "Default tutoring fallback."

  - event: EVT_RECOVERY_READY
    from: T_Anti_Mislead
    to: T_Probe_Recovery
    meaning: "Recovery bridge delivered; ask constrained follow-up."

  - event: EVT_CLARIFIED
    from: T_Concept_Clarify
    to: T_Probe_Retry
    meaning: "Concept clarified; retry same step."

  - event: EVT_REFOCUSED
    from: T_Affect_Repair
    to: T_Scaffold
    meaning: "Student stabilized; continue with scaffold."

  - event: EVT_OVERLOADED
    from: T_Affect_Repair
    to: T_Bailout
    meaning: "Affect repair failed; bail out."

  - event: EVT_HINT_EXHAUSTED
    from: T_Scaffold
    to: T_Bailout
    meaning: "Hint ladder exhausted."

  - event: EVT_VERIFY_PASS
    from: T_Verify
    to: T_Step_Advance_When_Ready
    meaning: "Verification passed."

  - event: EVT_VERIFY_FAIL
    from: T_Verify
    to: T_Scaffold
    meaning: "Verification failed; return to scaffold."

  - event: EVT_DIRECT_DONE
    from: T_Bailout_DirectExplain
    to: T_Verify
    meaning: "Current step directly explained; lightly verify if enabled."

  - event: EVT_ROLLBACK_REQUEST
    from: T_Bailout_Rollback
    to: P_Step_Tutor
    meaning: "Ask parent Problem-FSM to move current_step_order backward."

  - event: EVT_MARK_AND_MOVE
    from: T_Bailout_MarkAndMove
    to: T_Step_Advance_When_Ready
    meaning: "Mark weak mastery and continue."

interrupt_rules:
  global_interrupts:
    - source: ANY
      event: EVT_SESSION_PAUSE
      target: S_Session_Suspend
      rule: "Highest priority; persist all child snapshots."
    - source: ANY
      event: EVT_ABORT
      target: S_Session_End
      rule: "Terminate session gracefully."

  problem_interrupts:
    - source: P_ANY
      event: EVT_ABORT_PROBLEM
      target: P_Problem_Abort
      rule: "Abort only current problem, preserve session."

  step_interrupts:
    - source: T_ANY
      event: EVT_ROUTED_BAILOUT
      target: T_Bailout
      rule: "Overrides Scaffold/Probe loops."
    - source: T_Anti_Mislead
      event: EVT_STUDENT_REPLY
      target: T_Probe_Recovery
      rule: "Do not re-open broad probing after recovery."

priority_rules:
  router_priority:
    - mislead_hit
    - concept_question
    - affect_state_overloaded
    - needs_student_work
    - verify_needed
    - step_correctness_correct
    - bailout_threshold
    - default_scaffold

  verify_priority:
    - hard_verify_if_fast_guess
    - hard_verify_if_low_confidence
    - light_verify_if_normal_correct

  bailout_priority:
    - rollback_if_missing_prerequisite
    - direct_explain_if_current_step_teachable
    - mark_and_move_if_pacing_priority

return_contracts:
  from_step_to_problem:
    required_fields:
      - session_id
      - problem_id
      - current_step_id
      - emitted_event
      - trace_log_id
      - hint_level
      - attempt_count
  from_problem_to_session:
    required_fields:
      - session_id
      - problem_id
      - emitted_event
      - postmortem_id
      - learning_signal_ids

---

## 实现建议

这三份文件在工程里各自扮演的角色最好固定下来：
- `tutoring_v6.yaml`
    
    作为**单一真相源**，驱动状态机节点与转移规则
- `router.schema.json`
    
    作为 Router 输出校验器，保证后台判定结构稳定
- `fsm_events.yaml`
    
    作为父子状态机调度说明书，避免 Step / Problem / Session 混乱耦合
