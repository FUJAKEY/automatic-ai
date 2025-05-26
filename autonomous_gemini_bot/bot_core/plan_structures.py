from typing import TypedDict, List, Optional, Dict, Any

class ToolCallLogEntry(TypedDict):
    """
    Represents a log entry for a single tool call made as part of a ConceptualPlanStep.
    """
    tool_name: str
    args: Dict[str, Any]
    outcome_data: Optional[Any]  # Result from the tool if successful
    outcome_error: Optional[str] # Error message if the tool call failed
    timestamp: str               # ISO format string timestamp of the tool call

class ConceptualPlanStep(TypedDict):
    """
    Represents a single high-level step in a conceptual plan.
    This step might involve multiple tool calls to achieve its goal.
    """
    # Possible statuses:
    # 'pending': Not yet started.
    # 'in_progress': Actively being worked on by the executor.
    # 'achieved': Successfully completed.
    # 'unachievable': Goal deemed unachievable by planner.
    # 'failed_needs_correction': A tool call failed, or action limit reached, or planner stuck; main loop might try plan-level correction.
    # 'failed_terminal': Explicitly marked as a terminal failure that should not be corrected. (Consider if needed, or if 'unachievable' covers it)
    # --- New statuses based on goal_feedback ---
    # 'clarification_needed': Planner determined user clarification is required.
    # 'manual_intervention_requested': Planner determined manual help is needed.
    # 'code_generation_requested': Planner determined code generation is needed.
    # 'unsupported_action_identified': Planner determined the goal involves an unsupported action.

    step_id: str                 # Unique identifier for the step (e.g., UUID string)
    goal: str                    # High-level description of what this step aims to achieve
    status: str                  # Current status of the step (e.g., 'pending', 'in_progress', 'achieved', 'failed_terminal', 'failed_needs_correction', 'clarification_needed', etc.)
    reason_for_status: Optional[str] # Explanation for the current status (e.g., why it failed, or a summary if achieved)
    tool_logs: List[ToolCallLogEntry] # A log of all tool calls made in an attempt to achieve this step's goal
    final_result: Optional[Any]  # The overall result or consolidated output for this conceptual step, if applicable
    feedback_message: Optional[str] # Stores message_to_user if planner requests feedback/clarification

# Example of how ConceptualPlanStep might be initialized (for illustration):
# from uuid import uuid4
# from datetime import datetime, timezone
#
# initial_step = ConceptualPlanStep(
#     step_id=str(uuid4()),
#     goal="Find the 'docs' folder and identify its contents.",
#     status='pending',
#     reason_for_status=None,
#     tool_logs=[],
#     final_result=None
# )
#
# tool_log_entry_example = ToolCallLogEntry(
#    tool_name='list_directory_contents',
#    args={'path': '.'},
#    outcome_data=['file1.txt', 'my_folder/'],
#    outcome_error=None,
#    timestamp=datetime.now(timezone.utc).isoformat()
# )
