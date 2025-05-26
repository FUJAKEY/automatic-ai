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
    step_id: str                 # Unique identifier for the step (e.g., UUID string)
    goal: str                    # High-level description of what this step aims to achieve
    status: str                  # Current status of the step (e.g., 'pending', 'in_progress', 'achieved', 'failed_terminal', 'failed_needs_correction')
    reason_for_status: Optional[str] # Explanation for the current status (e.g., why it failed, or a summary if achieved)
    tool_logs: List[ToolCallLogEntry] # A log of all tool calls made in an attempt to achieve this step's goal
    final_result: Optional[Any]  # The overall result or consolidated output for this conceptual step, if applicable

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
