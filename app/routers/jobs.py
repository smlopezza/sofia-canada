import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException

from app.clients.claude_client import HAIKU, SONNET, call_claude_simple
from app.clients.email_client import send_daily_digest
from app.clients.firestore_client import get_all_contacts, get_all_users, get_mentors_since, get_waitlist_since, load_user, save_contact, save_user
from app.clients.twilio_client import send_message
from app.utils import is_sendable, local_hour

router = APIRouter()
logger = logging.getLogger(__name__)

SECRET = os.getenv("CLOUD_SCHEDULER_SECRET", "")

THANK_YOU_MSG = {
    "es": "¿Ya le mandaste un mensaje de agradecimiento a {name}? Es un gesto pequeño que hace una diferencia real. ¿Quieres que te ayude a escribirlo?",
    "en": "Did you send {name} a thank-you note? It's a small gesture that goes a long way. Want me to help you draft one?",
}

PRE_NUDGE_SYSTEM = (
    "You are SofIA, a warm bilingual ally for Latino newcomers to Canada. "
    "Generate a short, encouraging pre-chat nudge message for a user who has a professional "
    "coffee chat scheduled tomorrow. Include 2–3 specific prep questions tailored to the "
    "contact context provided. Keep it under 150 words. Never use the word 'networking'. "
    "IMPORTANT: No markdown formatting — no headers (#), no bold (**), no bullet symbols. "
    "Plain text only — this message is delivered via WhatsApp. "
    "Write entirely in the user's language — do not mix languages."
)

POST_CHECKIN_SYSTEM = (
    "You are SofIA, a warm bilingual ally for Latino newcomers to Canada. "
    "The user just had a professional coffee chat about 2 hours ago. "
    "Send a warm check-in asking how it went. Ask exactly ONE open Socratic question — "
    "a single question only, never two. Never declare what the relationship means or should be. "
    "Under 80 words. No markdown formatting — plain text only for WhatsApp."
)


def _verify(secret: str):
    if secret != SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


def _get_or_create_chat_entry(contact, scheduled_at: str) -> dict:
    """Return the chat entry matching scheduled_at, creating it if absent."""
    for entry in contact.chats:
        if entry.get("scheduled_at") == scheduled_at:
            return entry
    # Seed from top-level fields so single-chat contacts work without migration
    entry = {"scheduled_at": scheduled_at}
    if contact.post_nudge_sent_at:
        entry["post_nudge_sent_at"] = contact.post_nudge_sent_at
    if contact.pre_nudge_sent_at:
        entry["pre_nudge_sent_at"] = contact.pre_nudge_sent_at
    if contact.thank_you_nudge_sent_at:
        entry["thank_you_nudge_sent_at"] = contact.thank_you_nudge_sent_at
    contact.chats.append(entry)
    return entry


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _to_utc(dt_str: str) -> datetime | None:
    """Parse an ISO datetime string (with or without tz offset) into a UTC-naive datetime."""
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


@router.post("/jobs/pre-chat-nudge")
def pre_chat_nudge(x_scheduler_secret: str = Header(...)):
    _verify(x_scheduler_secret)
    now = datetime.utcnow()

    for phone, contact_id, contact in get_all_contacts():
        if not contact.scheduled_chat_at:
            continue
        chat_dt = _to_utc(contact.scheduled_chat_at)
        if not chat_dt or not (now + timedelta(hours=12) <= chat_dt <= now + timedelta(hours=36)):
            continue
        chat_entry = _get_or_create_chat_entry(contact, contact.scheduled_chat_at)
        if chat_entry.get("pre_nudge_sent_at"):
            continue

        user = load_user(phone)
        if user.opt_out_nudges:
            continue
        if not is_sendable(user.timezone) or local_hour(user.timezone) != 20:
            continue

        lang = "es" if user.language == "es" else "en"
        prompt = (
            f"User: {user.name}, field: {user.field}, language: {lang}.\n"
            f"Contact: {contact.name}, {contact.role} at {contact.company}.\n"
            f"Connection context: {contact.connection_context}.\n"
            f"Chat scheduled: {contact.scheduled_chat_at}.\n"
            f"Write the nudge in {lang}."
        )
        try:
            message = call_claude_simple(PRE_NUDGE_SYSTEM, prompt, model=HAIKU)
            send_message(phone, message)
            chat_entry["pre_nudge_sent_at"] = _now_iso()
            save_contact(phone, contact_id, contact)
        except Exception:
            logger.exception("Pre-chat nudge failed for %s / %s", phone, contact.name)

    return {"status": "ok"}


@router.post("/jobs/post-chat-checkin")
def post_chat_checkin(x_scheduler_secret: str = Header(...)):
    _verify(x_scheduler_secret)
    now = datetime.utcnow()

    for phone, contact_id, contact in get_all_contacts():
        if not contact.scheduled_chat_at:
            continue
        chat_dt = _to_utc(contact.scheduled_chat_at)
        if not chat_dt or not (now - timedelta(hours=3) <= chat_dt <= now - timedelta(hours=1)):
            continue
        chat_entry = _get_or_create_chat_entry(contact, contact.scheduled_chat_at)
        if chat_entry.get("post_nudge_sent_at"):
            continue

        user = load_user(phone)
        if user.opt_out_nudges:
            continue
        if not is_sendable(user.timezone):
            continue

        lang = "es" if user.language == "es" else "en"
        name_clause = (
            f"Address them as {user.name} in your greeting."
            if user.name
            else "Do not invent a name — greet warmly without using a name."
        )
        prompt = (
            f"You are sending this message to the user (field: {user.field}).\n"
            f"User name: '{user.name or 'unknown'}'.\n"
            f"They just had a chat with {contact.name}, {contact.role} at {contact.company}.\n"
            f"{name_clause} Never greet them as {contact.name}.\n"
            f"Write entirely in {lang}."
        )
        try:
            message = call_claude_simple(POST_CHECKIN_SYSTEM, prompt, model=SONNET)
            send_message(phone, message)
            chat_entry["post_nudge_sent_at"] = _now_iso()
            save_contact(phone, contact_id, contact)
        except Exception:
            logger.exception("Post-chat check-in failed for %s / %s", phone, contact.name)

    return {"status": "ok"}


@router.post("/jobs/thank-you-nudge")
def thank_you_nudge(x_scheduler_secret: str = Header(...)):
    _verify(x_scheduler_secret)
    now = datetime.utcnow()

    for phone, contact_id, contact in get_all_contacts():
        if not contact.scheduled_chat_at:
            continue
        chat_dt = _to_utc(contact.scheduled_chat_at)
        if not chat_dt or not (now - timedelta(hours=36) <= chat_dt <= now - timedelta(hours=12)):
            continue
        chat_entry = _get_or_create_chat_entry(contact, contact.scheduled_chat_at)
        if chat_entry.get("thank_you_nudge_sent_at"):
            continue
        if not chat_entry.get("post_nudge_sent_at"):
            continue

        user = load_user(phone)
        if user.opt_out_nudges:
            continue
        if local_hour(user.timezone) != 7:
            continue

        lang = user.language if user.language in THANK_YOU_MSG else "es"
        message = THANK_YOU_MSG[lang].format(name=contact.name)
        try:
            send_message(phone, message)
            chat_entry["thank_you_nudge_sent_at"] = _now_iso()
            save_contact(phone, contact_id, contact)
        except Exception:
            logger.exception("Thank-you nudge failed for %s / %s", phone, contact.name)

    return {"status": "ok"}


@router.post("/jobs/daily-digest")
def daily_digest(x_scheduler_secret: str = Header(...)):
    _verify(x_scheduler_secret)
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=24)).isoformat()
    date_label = now.strftime("%Y-%m-%d")

    waitlist_entries = get_waitlist_since(cutoff)
    new_mentors = get_mentors_since(cutoff)

    if not waitlist_entries and not new_mentors:
        logger.info("Daily digest: nothing new, skipping email")
        return {"status": "ok", "sent": False}

    sent = send_daily_digest(waitlist_entries, new_mentors, date_label)
    return {"status": "ok", "sent": sent, "waitlist": len(waitlist_entries), "mentors": len(new_mentors)}


@router.post("/jobs/reset-rate-limits")
def reset_rate_limits(x_scheduler_secret: str = Header(...)):
    _verify(x_scheduler_secret)
    now_iso = datetime.utcnow().isoformat()
    reset_count = 0

    for user in get_all_users():
        if user.message_count_reset_at and user.message_count_reset_at < now_iso:
            user.message_count_today = 0
            next_midnight = (datetime.utcnow() + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            user.message_count_reset_at = next_midnight.isoformat()
            save_user(user)
            reset_count += 1

    return {"status": "ok", "reset": reset_count}
