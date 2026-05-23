import logging
import re
import time
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import Response

from app.models import ContactDoc
from app.claude_client import (
    SONNET,
    build_context,
    call_claude,
    continue_with_tool_result,
    generate_summary,
)
from app.firestore_client import (
    get_active_contact,
    get_user_contacts,
    is_duplicate,
    load_user,
    save_contact,
    save_user,
)
from app.prompts import SYSTEM_PROMPT
from app.twilio_client import send_message
from langfuse import Langfuse

router = APIRouter()
logger = logging.getLogger(__name__)

_langfuse = Langfuse()

RATE_LIMITS = {"free": 30, "contributor": 50, "org_sponsored": 99999}

RATE_LIMIT_MSG = {
    "es": (
        "Ya usaste tus mensajes de hoy — vuelve mañana. "
        "Si quieres acceso ilimitado, puedes contribuir a la comunidad: [link]. "
        "Si no puedes, está bien."
    ),
    "en": (
        "You've used today's messages — come back tomorrow. "
        "If you'd like unlimited access, you can support the community here: [link]. "
        "No pressure if not."
    ),
}

ERROR_MSG = {
    "es": "Algo salió mal de mi lado — intenta de nuevo en un momento.",
    "en": "Something went wrong on my end — try again in a moment.",
}


@router.post("/webhook/twilio")
async def twilio_webhook(request: Request, background_tasks: BackgroundTasks):
    form = await request.form()
    phone = str(form.get("From", "")).replace("whatsapp:", "")
    text = str(form.get("Body", ""))
    message_sid = str(form.get("MessageSid", ""))

    background_tasks.add_task(_process_safely, phone, text, message_sid)
    return Response(content="", media_type="text/xml")


def _process_safely(phone: str, text: str, message_sid: str):
    try:
        _process(phone, text, message_sid)
    except Exception:
        logger.exception("Unhandled error processing message for %s", phone)
    finally:
          _langfuse.flush()


def _find_mentioned_contact(text: str, all_contacts: list, active_contact) -> "ContactDoc | None":
    """Return the first contact whose first name appears in the message, if not already active."""
    text_lower = text.lower()
    for c in all_contacts:
        if active_contact and c.name == active_contact.name:
            continue
        first_name = c.name.split()[0].lower()
        if len(first_name) >= 3 and first_name in text_lower:
            return c
    return None


def _process(phone: str, text: str, message_sid: str):
    if is_duplicate(message_sid):
        return

    user = load_user(phone)
    now = datetime.utcnow()

    if not _check_and_increment_rate_limit(user, now):
        send_message(phone, RATE_LIMIT_MSG.get(user.language, RATE_LIMIT_MSG["es"]))
        save_user(user)
        return

    contact_id, contact = get_active_contact(phone)
    all_contacts = [c for _, c in get_user_contacts(phone)]
    mentioned = _find_mentioned_contact(text, all_contacts, contact)
    context = build_context(user, contact, all_contacts, mentioned)
    claude_messages = _build_messages(user, context, text)

    reply = _call_with_retry(user, contact, contact_id, phone, claude_messages)
    if not reply:
        reply = ERROR_MSG.get(user.language, ERROR_MSG["es"])

    ts = now.isoformat()
    user.messages.append({"role": "user", "content": text, "timestamp": ts})
    user.messages.append({"role": "assistant", "content": reply, "timestamp": ts})
    if len(user.messages) > 20:
        user.messages = user.messages[-20:]
    user.last_active = ts
    save_user(user)

    send_message(phone, reply)

    if len(user.messages) >= 20:
        try:
            user.conversation_summary = generate_summary(user)
            user.messages = []
            user.last_compression_at = ts
            save_user(user)
        except Exception:
            logger.exception("Summary generation failed for %s", phone)


def _call_with_retry(user, contact, contact_id, phone, claude_messages) -> str:
    for attempt in range(2):
        try:
            return _call_claude_and_apply(user, contact, contact_id, phone, claude_messages)
        except Exception:
            if attempt == 0:
                logger.warning("Claude call failed for %s, retrying", phone)
                time.sleep(2)
            else:
                logger.exception("Claude retry failed for %s", phone)
    return ""


def _call_claude_and_apply(user, contact, contact_id, phone, claude_messages) -> str:
    reply, assistant_content, tool_use_id, tool_inputs = call_claude(
        SYSTEM_PROMPT, claude_messages, model=SONNET
    )

    if tool_inputs and tool_use_id:
        contact, contact_id = _apply_tool_use(user, contact, contact_id, phone, tool_inputs)
        save_user(user)
        if contact and contact_id:
            save_contact(phone, contact_id, contact)

        tool_result_content = "ok"
        export_link = getattr(user, "_export_link", None)
        if export_link:
            tool_result_content = f"ok. Export link generated: {export_link}"
            del user._export_link

        reply = continue_with_tool_result(
            SYSTEM_PROMPT, claude_messages, assistant_content, tool_use_id,
            tool_result=tool_result_content, model=SONNET
        )

    return reply


def _build_messages(user, context: str, new_text: str) -> list:
    """Build Claude messages with context injected as prefix of the first user turn."""
    history = [{"role": m["role"], "content": m["content"]} for m in user.messages]
    if history:
        first = history[0]
        history[0] = {"role": "user", "content": f"{context}\n\n{first['content']}"}
        return history + [{"role": "user", "content": new_text}]
    return [{"role": "user", "content": f"{context}\n\n{new_text}"}]


def _check_and_increment_rate_limit(user, now: datetime) -> bool:
    """Returns True if within limit. Mutates user to reset counter if needed and increment."""
    if user.message_count_reset_at is None or user.message_count_reset_at < now.isoformat():
        user.message_count_today = 0
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        user.message_count_reset_at = next_midnight.isoformat()

    limit = RATE_LIMITS.get(user.tier, 30)
    if user.message_count_today >= limit:
        return False

    user.message_count_today += 1
    return True


def _apply_tool_use(user, contact, contact_id, phone, tool_inputs: dict) -> tuple:
    """Apply update_state tool inputs. Returns (contact, contact_id)."""
    logger.info("update_state called for %s: %s", phone, tool_inputs)

    new_contact_data = tool_inputs.get("new_contact")
    if new_contact_data and not contact:
        contact = ContactDoc(
            name=new_contact_data.get("name", ""),
            role=new_contact_data.get("role", ""),
            company=new_contact_data.get("company", ""),
            connection_context=new_contact_data.get("connection_context", ""),
            scheduled_chat_at=new_contact_data.get("scheduled_chat_at"),
            created_at=datetime.utcnow().isoformat(),
        )
        contact_id = str(uuid.uuid4())
        user.has_contacts = True
        user.contact_count += 1
        logger.info("New contact created for %s: %s at %s", phone, contact.name, contact.scheduled_chat_at)
    elif new_contact_data and contact:
        logger.info("new_contact skipped for %s — contact already exists: %s", phone, contact.name)

    new_state = tool_inputs.get("new_state")
    if new_state:
        user.current_state = new_state

    about_me = tool_inputs.get("about_me")
    if about_me and not user.about_me:
        user.about_me = about_me

    country_of_origin = tool_inputs.get("country_of_origin")
    if country_of_origin and not user.country_of_origin:
        user.country_of_origin = country_of_origin

    contact_updates = tool_inputs.get("contact_updates")
    if contact_updates and contact:
        add_chat = contact_updates.get("add_chat")
        if add_chat:
            contact.chats.append(add_chat)
            if add_chat.get("scheduled_at"):
                contact.scheduled_chat_at = add_chat["scheduled_at"]
                logger.info("Chat scheduled for %s: %s at %s", phone, contact.name, contact.scheduled_chat_at)
        for field, value in contact_updates.items():
            if field == "add_chat":
                continue
            if field == "is_mentor" and hasattr(contact, "is_mentor"):
                if value and not contact.is_mentor:
                    user.mentor_count += 1
                elif not value and contact.is_mentor:
                    user.mentor_count = max(0, user.mentor_count - 1)
            if hasattr(contact, field):
                setattr(contact, field, value)
    elif contact_updates and not contact:
        logger.warning("contact_updates dropped for %s — no contact exists yet: %s", phone, contact_updates)

    opt_out_nudges = tool_inputs.get("opt_out_nudges")
    if opt_out_nudges is not None:
        user.opt_out_nudges = opt_out_nudges
        logger.info("opt_out_nudges set to %s for %s", opt_out_nudges, phone)

    goals = tool_inputs.get("goals")
    if goals:
        existing = set(user.goals or [])
        for g in goals:
            if g not in existing:
                user.goals.append(g)

    if tool_inputs.get("export_requested"):
        from app.export import generate_export_token
        token_id, link = generate_export_token(phone)
        logger.info("Export token generated for %s: %s", phone, token_id)
        user._export_link = link

    return contact, contact_id
