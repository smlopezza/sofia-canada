import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import Response

from app.models import ContactDoc
from app.clients.claude_client import (
    build_context,
    call_claude,
    generate_summary,
)
from app.clients.firestore_client import (
    count_active_users,
    get_active_contact,
    get_user_contacts,
    is_duplicate,
    load_user,
    save_contact,
    save_user,
)
from app.prompts import SYSTEM_PROMPT
from app.clients.twilio_client import send_message
from langfuse import Langfuse
from langfuse.decorators import langfuse_context

router = APIRouter()
logger = logging.getLogger(__name__)

_langfuse = Langfuse()

RATE_LIMITS = {"free": 30, "contributor": 50, "org_sponsored": 99999, "test": 99999}

RATE_LIMIT_MSG = {
    "es": (
        "Ya usaste tus mensajes de hoy — vuelve mañana. "
        "Si quieres acceso ilimitado, puedes contribuir a la comunidad: buymeacoffee.com/sofia_canada "
        "Si no puedes, está bien."
    ),
    "en": (
        "You've used today's messages — come back tomorrow. "
        "If you'd like unlimited access, you can support the community here: buymeacoffee.com/sofia_canada. "
        "No pressure if not."
    ),
}

ERROR_MSG = {
    "es": "Algo salió mal de mi lado — intenta de nuevo en un momento.",
    "en": "Something went wrong on my end — try again in a moment.",
}

MAX_USERS = int(os.getenv("MAX_USERS", "20"))

MILESTONE_LABELS = {
    "en": {
        "active_job_search": "Actively applying",
        "first_contact_registered": "First contact registered",
        "first_chat_scheduled": "First coffee chat scheduled",
        "first_chat_completed": "First coffee chat completed",
        "building_momentum": "Building momentum",
        "deepening_relationships": "Deepening relationships",
        "mentor_identified": "Mentor identified ⭐",
        "interview_stage": "First interview",
        "advancing_in_interviews": "Advancing in interviews",
        "job_offer_received": "Job offer received",
        "job_landed": "Job landed! 🎉",
        "first_90_days": "First 90 days on the job",
    },
    "es": {
        "active_job_search": "Aplicando activamente",
        "first_contact_registered": "Primer contacto registrado",
        "first_chat_scheduled": "Primer coffee chat agendado",
        "first_chat_completed": "Primer coffee chat completado",
        "building_momentum": "Construyendo momentum",
        "deepening_relationships": "Profundizando relaciones",
        "mentor_identified": "Mentor identificado ⭐",
        "interview_stage": "Primera entrevista",
        "advancing_in_interviews": "Avanzando en entrevistas",
        "job_offer_received": "Oferta recibida",
        "job_landed": "¡Trabajo conseguido! 🎉",
        "first_90_days": "Primeros 90 días en el trabajo",
    },
}

WAITLIST_MSG = (
    "Hola / Hi! 👋\n\n"
    "SofIA está en beta cerrada por ahora — SofIA is currently in closed beta.\n\n"
    "Únete a la lista de espera / Join the waitlist:\n"
    "👉 https://sofia-qhgvxxwh5q-nn.a.run.app\n\n"
    "Te avisaremos cuando haya espacio. We'll reach out when a spot opens up. 🌟"
)


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
        langfuse_context.flush()


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

    # Bounce new users if beta is full
    if user.last_active is None and user.tier != "test" and count_active_users() >= MAX_USERS:
        logger.info("Beta full — bouncing new user %s to waitlist", phone)
        send_message(phone, WAITLIST_MSG)
        return
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
                time.sleep(4)
            else:
                logger.exception("Claude retry failed for %s", phone)
    return ""


def _call_claude_and_apply(user, contact, contact_id, phone, claude_messages) -> str:
    reply, tool_inputs = call_claude(SYSTEM_PROMPT, list(claude_messages))

    if tool_inputs:
        contact, contact_id = _apply_tool_use(user, contact, contact_id, phone, tool_inputs)
        save_user(user)
        if contact and contact_id:
            save_contact(phone, contact_id, contact)

        export_link = getattr(user, "_export_link", None)
        if export_link:
            del user._export_link
            reply = f"{reply}\n\n{export_link}"

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
    if new_contact_data:
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
        logger.info("New contact created for %s: %s", phone, contact.name)

    new_state = tool_inputs.get("new_state")
    if new_state and new_state != user.current_state:
        user.current_state = new_state
        labels = MILESTONE_LABELS.get(user.language or "es", MILESTONE_LABELS["en"])
        if new_state in labels:
            existing_keys = {m.get("key") for m in (user.milestones or []) if isinstance(m, dict)}
            if new_state not in existing_keys:
                user.milestones.append({
                    "key": new_state,
                    "label": labels[new_state],
                    "achieved_at": datetime.utcnow().isoformat(),
                    "note": "",
                })
                logger.info("Milestone saved for %s: %s", phone, new_state)
    elif new_state:
        user.current_state = new_state

    about_me = tool_inputs.get("about_me")
    if about_me and not user.about_me:
        user.about_me = about_me

    user_name = tool_inputs.get("user_name")
    if user_name and not user.name:
        user.name = user_name
        logger.info("User name set for %s: %s", phone, user_name)

    country_of_origin = tool_inputs.get("country_of_origin")
    if country_of_origin and not user.country_of_origin:
        user.country_of_origin = country_of_origin

    city = tool_inputs.get("city")
    if city and not user.city:
        user.city = city
        logger.info("City set for %s: %s", phone, city)

    field = tool_inputs.get("field")
    if field and not user.field:
        user.field = field
        logger.info("Field set for %s: %s", phone, field)

    time_in_canada = tool_inputs.get("time_in_canada")
    if time_in_canada and not user.time_in_canada:
        user.time_in_canada = time_in_canada
        logger.info("Time in Canada set for %s: %s", phone, time_in_canada)

    language = tool_inputs.get("language")
    if language:
        user.language = language
        logger.info("Language set for %s: %s", phone, language)

    transition_stage = tool_inputs.get("transition_stage")
    if transition_stage:
        user.transition_stage = transition_stage
        logger.info("transition_stage set for %s: %s", phone, transition_stage)

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

    milestones_to_save = tool_inputs.get("milestones")
    if milestones_to_save and isinstance(milestones_to_save, list):
        existing_keys = {m.get("key") for m in (user.milestones or []) if isinstance(m, dict)}
        for m in milestones_to_save:
            key = m.get("key", "").strip()
            label = m.get("label", "").strip()
            if key and label and key not in existing_keys:
                user.milestones.append({
                    "key": key,
                    "label": label,
                    "achieved_at": datetime.utcnow().isoformat(),
                    "note": m.get("note", ""),
                })
                existing_keys.add(key)
                logger.info("Milestone explicitly saved for %s: %s", phone, key)

    new_learning = tool_inputs.get("new_learning")
    if new_learning and isinstance(new_learning, dict):
        insight = new_learning.get("insight", "").strip()
        topic = new_learning.get("topic", "")
        if insight and topic:
            existing_insights = {
                m.get("insight") for m in (user.learnings or []) if isinstance(m, dict)
            }
            if insight not in existing_insights:
                user.learnings.append({
                    "id": str(uuid.uuid4()),
                    "topic": topic,
                    "insight": insight,
                    "confidence": new_learning.get("confidence", "medium"),
                    "saved_at": datetime.utcnow().isoformat(),
                    "source_context": "",
                    "user_flagged": False,
                })
                logger.info("Learning saved for %s: [%s] %s", phone, topic, insight[:60])

    if tool_inputs.get("export_requested"):
        from app.routers.profile import generate_export_token
        token_id, link = generate_export_token(phone)
        logger.info("Export token generated for %s: %s", phone, token_id)
        user._export_link = link

    return contact, contact_id
