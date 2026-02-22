from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SessionState:
    session_id: str
    messages: list = field(default_factory=list)  # Anthropic API format
    target_url: str = ""
    current_url: str = ""
    demo_stage: str = "greeting"
    is_authenticated: bool = False
    last_screenshot_b64: Optional[str] = None
