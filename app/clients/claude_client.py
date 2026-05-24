import os
from datetime import datetime
from zoneinfo import ZoneInfo
import anthropic
from app.models import UserDoc, ContactDoc
from langfuse.decorators import observe, langfuse_context

_client = None

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def build_context(user: UserDoc, contact: ContactDoc | None, all_contacts: list[ContactDoc] | None = None, mentioned_contact: ContactDoc | None = None) -> str:
    try:
        tz = ZoneInfo(user.timezone or "America/Toronto")
        now_local = datetime.now(tz)
        current_date = now_local.strftime("%Y-%m-%d (%A)")
    except Exception:
        current_date = datetime.utcnow().strftime("%Y-%m-%d")

    parts = [
        f"[CURRENT DATE: {current_date} — user timezone: {user.timezone or 'America/Toronto'}]",
        "[USER PROFILE]",
        f"Name: {user.name}",
        f"Field: {user.field}",
        f"Language: {user.language}",
        f"Time in Canada: {user.time_in_canada}",
        f"City: {user.city}",
        f"Country of origin: {user.country_of_origin}",
        f"Current challenge: {user.current_challenge}",
        f"Current state: {user.current_state}",
    ]
    if user.about_me:
        parts.append(f"About me: {user.about_me}")
    if user.conversation_summary:
        parts.append(f"Conversation summary: {user.conversation_summary}")

    if contact:
        parts += [
            "\n[ACTIVE CONTACT]",
            f"Name: {contact.name}, {contact.role} at {contact.company}",
            f"Connection context: {contact.connection_context}",
            f"Is mentor: {'Yes' if contact.is_mentor else 'No'}",
            f"Next chat scheduled: {contact.scheduled_chat_at or 'none'}",
            f"Topics of interest: {', '.join(contact.topics_of_interest) if contact.topics_of_interest else 'none'}",
            f"Post-call notes: {contact.post_call_notes or 'none yet'}",
        ]
        if contact.linkedin_url:
            parts.append(f"LinkedIn: {contact.linkedin_url}")
        if contact.chats:
            chats_to_show = contact.chats[-5:]
            parts.append(f"\nCoffee chat history ({len(contact.chats)} total, showing last {len(chats_to_show)}):")
            for i, chat in enumerate(chats_to_show, 1):
                line = f"  Chat {i}: {chat.get('scheduled_at', 'date unknown')}"
                if chat.get('notes'):
                    line += f" — {chat['notes']}"
                if chat.get('depth_signals'):
                    line += f" (signals: {chat['depth_signals']})"
                parts.append(line)

    if mentioned_contact:
        parts += [
            "\n[MENTIONED CONTACT — user referred to this person in their message]",
            f"Name: {mentioned_contact.name}, {mentioned_contact.role} at {mentioned_contact.company}",
            f"Connection context: {mentioned_contact.connection_context}",
            f"Is mentor: {'Yes' if mentioned_contact.is_mentor else 'No'}",
            f"Post-call notes: {mentioned_contact.post_call_notes or 'none yet'}",
        ]
        if mentioned_contact.chats:
            chats_to_show = mentioned_contact.chats[-5:]
            parts.append(f"Coffee chat history ({len(mentioned_contact.chats)} total, showing last {len(chats_to_show)}):")
            for i, chat in enumerate(chats_to_show, 1):
                line = f"  Chat {i}: {chat.get('scheduled_at', 'date unknown')}"
                if chat.get('notes'):
                    line += f" — {chat['notes']}"
                if chat.get('depth_signals'):
                    line += f" (signals: {chat['depth_signals']})"
                parts.append(line)

    if all_contacts and contact:
        mentioned_name = mentioned_contact.name if mentioned_contact else None
        others = [c for c in all_contacts if c.name != contact.name and c.name != mentioned_name]
        if others:
            parts.append("\n[OTHER CONTACTS]")
            for c in others:
                chat_count = len(c.chats) if c.chats else 0
                suffix = " — mentor" if c.is_mentor else ""
                if c.is_mentor or chat_count >= 2:
                    parts.append(f"  {c.name} — {c.role} at {c.company} ({chat_count} meetings{suffix})")
                    if c.post_call_notes:
                        parts.append(f"    Notes: {c.post_call_notes}")
                else:
                    parts.append(f"  {c.name} — {c.role} at {c.company} (1 meeting)")

    return "\n".join(parts)

@observe(as_type="generation")
def _make_request(system: str, messages: list, model: str) -> anthropic.types.Message:
    from app.prompts import TOOLS
    response = get_client().messages.create(
        model=model,
        max_tokens=1024,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        tools=TOOLS,
        messages=messages,
    )
    langfuse_context.update_current_observation(
          model=model,
          input=messages,
          output=[b.text for b in response.content if b.type == "text"],
          usage={
              "input": response.usage.input_tokens,
              "output": response.usage.output_tokens,
          },  
      )   
    return response


def call_claude(system: str, messages: list, model: str = SONNET) -> tuple[str, list, str | None, dict | None]:
    """
    Returns (text, response_content, tool_use_id | None, tool_inputs | None).
    response_content is the raw assistant turn needed to continue the conversation after tool use.
    """
    response = _make_request(system, messages, model)
    text = ""
    tool_use_id = None
    tool_inputs = None
    for block in response.content:
        if block.type == "tool_use":
            tool_use_id = block.id
            tool_inputs = block.input
        elif block.type == "text":
            text = block.text
    return text, response.content, tool_use_id, tool_inputs


def continue_with_tool_result(
    system: str,
    messages: list,
    assistant_content: list,
    tool_use_id: str,
    tool_result: str = "ok",
    model: str = SONNET,
) -> str:
    """Send tool_result back to Claude and return the final text response."""
    extended = messages + [
        {"role": "assistant", "content": assistant_content},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": tool_result}]},
    ]
    response = _make_request(system, extended, model)
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""

@observe(as_type="generation")
def generate_summary(user: UserDoc) -> str:
    existing = f"Existing summary:\n{user.conversation_summary}\n\n" if user.conversation_summary else ""
    content = f"{existing}New messages to incorporate:\n{str(user.messages)}"
    response = get_client().messages.create(
        model=SONNET,
        max_tokens=1024,
        system=(
            "Update the conversation summary by incorporating the new messages. "
            "If an existing summary is provided, build on it — do not replace it. "
            "Capture: user's name, field, country of origin, time in Canada, current state, "
            "key contacts discussed (name, role, company, relationship depth, any depth signals), "
            "important moments (milestones, near-quit moments, emotional shifts, breakthroughs), "
            "cultural insights or reframes that landed, open threads and next steps. "
            "Write in third person. Up to 500 words — use the space to preserve emotional texture, "
            "not just facts. What made this person hesitate, what gave them confidence, "
            "what they're still working through."
        ),
        messages=[{"role": "user", "content": content}],
    )

    langfuse_context.update_current_observation(
          model=SONNET,
          input=user.messages,
          output=response.content[0].text,
          usage={
              "input": response.usage.input_tokens,
              "output": response.usage.output_tokens,
          },
    )

    return response.content[0].text

@observe(as_type="generation")
def call_claude_simple(system: str, prompt: str, model: str = HAIKU) -> str:
    """Single-turn call without tools — used by proactive job endpoints."""
    response = get_client().messages.create(
        model=model,
        max_tokens=512,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    )

    langfuse_context.update_current_observation(
          model=model,
          input=prompt,
          output=response.content[0].text if response.content else "",
          usage={
              "input": response.usage.input_tokens,
              "output": response.usage.output_tokens,
          },
    )
    
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""

