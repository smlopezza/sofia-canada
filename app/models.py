from dataclasses import dataclass
from typing import Optional


@dataclass
class Milestone:
    # A milestone or goal checkpoint the user has achieved.
    key: str
    label: str
    achieved_at: str
    note: str = ""


@dataclass
class Learning:
    # A saved learning or insight captured by the user.
    id: str
    topic: str
    insight: str
    saved_at: str
    source_context: str = ""  # optional info about where the learning came from
    confidence: str = "medium"  # expected values: "high" | "medium" | "uncertain"
    user_flagged: bool = False  # whether the user marked this learning as important


@dataclass
class MentorDoc:
    # Mentor profile document stored for mentor management.
    name: str
    email: str
    role: str = ""
    company: str = ""
    industry: str = ""
    city: str = ""
    country_of_origin: str = ""
    linkedin: str = ""
    calendly: str = ""
    contact_preference: str = "linkedin"  # preferred way to contact the mentor
    languages: Optional[list] = None
    bio: str = ""
    active: bool = True
    opt_out_token: str = ""  # token used when a mentor opts out of notifications
    created_at: str = ""

    def __post_init__(self):
        # Ensure list fields are always initialized as lists, not None.
        if self.languages is None:
            self.languages = []


@dataclass
class ExportToken:
    # Token used for exporting user data or validating an export request.
    phone: str
    created_at: str
    expires_at: str
    used: bool = False


@dataclass
class ContactDoc:
    # Stored contact or networking connection associated with a user.
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
        # Initialize list fields to empty lists when no data is provided.
        if self.topics_of_interest is None:
            self.topics_of_interest = []
        if self.chats is None:
            self.chats = []


@dataclass
class UserDoc:
    # Main user profile document used for app state and metadata.
    phone: str
    name: str = ""
    field: str = ""  # user’s professional or academic field
    language: str = "es"
    time_in_canada: str = ""
    transition_stage: str = ""
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
    profile_link_sent: bool = False
    session_id: Optional[str] = None
    session_message_count: int = 0

    def __post_init__(self):
        # Initialize optional list fields to avoid None checks elsewhere.
        if self.messages is None:
            self.messages = []
        if self.goals is None:
            self.goals = []
        if self.milestones is None:
            self.milestones = []
        if self.learnings is None:
            self.learnings = []
