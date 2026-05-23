from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Milestone:
    key: str
    label: str
    achieved_at: str
    note: str = ""


@dataclass
class Learning:
    id: str
    topic: str
    insight: str
    saved_at: str
    source_context: str = ""
    confidence: str = "medium"  # "high" | "medium" | "uncertain"
    user_flagged: bool = False


@dataclass
class ExportToken:
    phone: str
    created_at: str
    expires_at: str
    used: bool = False


@dataclass
class ContactDoc:
    name: str
    role: str
    company: str
    connection_context: str
    scheduled_chat_at: Optional[str] = None
    pre_nudge_sent_at: Optional[str] = None
    post_nudge_sent_at: Optional[str] = None
    thank_you_nudge_sent_at: Optional[str] = None
    post_call_notes: Optional[str] = None
    depth_signals: Optional[str] = None
    topics_of_interest: Optional[list] = None
    linkedin_url: Optional[str] = None
    created_at: Optional[str] = None
    is_mentor: bool = False
    chats: Optional[list] = None

    def __post_init__(self):
        if self.topics_of_interest is None:
            self.topics_of_interest = []
        if self.chats is None:
            self.chats = []


@dataclass
class UserDoc:
    phone: str
    name: str = ""
    field: str = ""
    language: str = "es"
    time_in_canada: str = ""
    city: str = ""
    country_of_origin: str = ""
    timezone: str = "America/Toronto"
    current_challenge: str = ""
    has_contacts: bool = False
    contact_count: int = 0
    mentor_count: int = 0
    about_me: Optional[str] = None
    conversation_summary: Optional[str] = None
    current_state: str = "onboarding"
    messages: Optional[list] = None
    last_active: Optional[str] = None
    tier: str = "free"
    message_count_today: int = 0
    message_count_reset_at: Optional[str] = None
    contributed_at: Optional[str] = None
    is_volunteering: bool = False
    goals: Optional[list] = None
    milestones: Optional[list] = None
    learnings: Optional[list] = None
    opt_out_nudges: bool = False
    last_compression_at: Optional[str] = None

    def __post_init__(self):
        if self.messages is None:
            self.messages = []
        if self.goals is None:
            self.goals = []
        if self.milestones is None:
            self.milestones = []
        if self.learnings is None:
            self.learnings = []
