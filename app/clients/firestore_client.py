import os
import logging
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from app.models import UserDoc, ContactDoc, ExportToken

_db = None
logger = logging.getLogger(__name__)

_USER_FIELDS = {f for f in UserDoc.__dataclass_fields__} - {"application_stage"}
_CONTACT_FIELDS = {f for f in ContactDoc.__dataclass_fields__}


def get_db():
    global _db
    if _db is None:
        _db = firestore.Client(project=os.getenv("FIRESTORE_PROJECT_ID"))
    return _db


def _to_str(val) -> str | None:
    """Convert Firestore Timestamp or other types to ISO string."""
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _safe_user_data(data: dict) -> dict:
    """Strip unknown fields and convert timestamps for UserDoc."""
    out = {k: v for k, v in data.items() if k in _USER_FIELDS}
    for ts_field in ("last_active", "message_count_reset_at", "contributed_at", "last_compression_at"):
        if ts_field in out:
            out[ts_field] = _to_str(out[ts_field])
    for list_field in ("goals", "milestones", "learnings", "messages"):
        if list_field in out and out[list_field] is None:
            out[list_field] = []
    return out


def _safe_contact_data(data: dict) -> dict:
    """Strip unknown fields and convert timestamps for ContactDoc."""
    out = {k: v for k, v in data.items() if k in _CONTACT_FIELDS}
    for ts_field in ("scheduled_chat_at", "pre_nudge_sent_at", "post_nudge_sent_at",
                     "thank_you_nudge_sent_at", "created_at"):
        if ts_field in out:
            out[ts_field] = _to_str(out[ts_field])
    return out


def load_user(phone: str) -> UserDoc:
    doc = get_db().collection("users").document(phone).get()
    if doc.exists:
        return UserDoc(phone=phone, **_safe_user_data(doc.to_dict()))
    return UserDoc(phone=phone)


def save_user(user: UserDoc):
    data = {k: v for k, v in user.__dict__.items() if k != "phone" and not k.startswith("_")}
    get_db().collection("users").document(user.phone).set(data, merge=True)


def get_active_contact(phone: str) -> tuple[str | None, ContactDoc | None]:
    """Returns (contact_id, ContactDoc) for the most recently created contact, or (None, None)."""
    try:
        docs = list(
            get_db().collection("users").document(phone)
            .collection("contacts")
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(1)
            .stream()
        )
    except Exception:
        # If no index exists yet, fall back to unordered
        docs = list(
            get_db().collection("users").document(phone)
            .collection("contacts")
            .limit(1)
            .stream()
        )
    for doc in docs:
        try:
            return doc.id, ContactDoc(**_safe_contact_data(doc.to_dict()))
        except Exception:
            logger.exception("Failed to load contact %s for %s", doc.id, phone)
    return None, None


def get_user_contacts(phone: str) -> list[tuple[str, ContactDoc]]:
    """Returns all (contact_id, ContactDoc) for a single user."""
    results = []
    for doc in get_db().collection("users").document(phone).collection("contacts").stream():
        try:
            results.append((doc.id, ContactDoc(**_safe_contact_data(doc.to_dict()))))
        except Exception:
            logger.exception("Failed to load contact %s for %s", doc.id, phone)
    return results


def load_contact(phone: str, contact_id: str) -> ContactDoc | None:
    doc = get_db().collection("users").document(phone)\
        .collection("contacts").document(contact_id).get()
    if doc.exists:
        return ContactDoc(**_safe_contact_data(doc.to_dict()))
    return None


def save_contact(phone: str, contact_id: str, contact: ContactDoc):
    get_db().collection("users").document(phone)\
        .collection("contacts").document(contact_id).set(contact.__dict__, merge=True)


def update_contact_fields(phone: str, contact_id: str, updates: dict):
    get_db().collection("users").document(phone)\
        .collection("contacts").document(contact_id).update(updates)


def delete_contact(phone: str, contact_id: str):
    get_db().collection("users").document(phone)\
        .collection("contacts").document(contact_id).delete()


def is_duplicate(message_sid: str) -> bool:
    doc = get_db().collection("processed_messages").document(message_sid).get()
    if doc.exists:
        return True
    get_db().collection("processed_messages").document(message_sid).set({"processed": True})
    return False


def get_all_contacts() -> list[tuple[str, str, ContactDoc]]:
    """Returns (phone, contact_id, ContactDoc) for all contacts across all users."""
    results = []
    for user_doc in get_db().collection("users").stream():
        phone = user_doc.id
        for contact_doc in get_db().collection("users").document(phone).collection("contacts").stream():
            try:
                results.append((phone, contact_doc.id, ContactDoc(**_safe_contact_data(contact_doc.to_dict()))))
            except Exception:
                logger.exception("Failed to load contact %s/%s", phone, contact_doc.id)
    return results


def get_all_users() -> list[UserDoc]:
    """Returns all user documents."""
    users = []
    for doc in get_db().collection("users").stream():
        try:
            users.append(UserDoc(phone=doc.id, **_safe_user_data(doc.to_dict())))
        except Exception:
            logger.exception("Failed to load user %s", doc.id)
    return users


def save_export_token(token_id: str, token: ExportToken):
    get_db().collection("export_tokens").document(token_id).set(token.__dict__)


def get_export_token(token_id: str) -> ExportToken | None:
    doc = get_db().collection("export_tokens").document(token_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    for ts_field in ("created_at", "expires_at"):
        if ts_field in data:
            data[ts_field] = _to_str(data[ts_field])
    return ExportToken(**data)


def mark_export_token_used(token_id: str):
    get_db().collection("export_tokens").document(token_id).update({"used": True})


def save_waitlist_entry(entry: dict) -> str:
    ref = get_db().collection("waitlist").document()
    ref.set(entry)
    return ref.id


def get_waitlist_by_email(email: str) -> bool:
    docs = list(get_db().collection("waitlist").where(filter=FieldFilter("email", "==", email.lower())).stream())
    return len(docs) > 0


def get_waitlist_since(cutoff_iso: str) -> list[dict]:
    docs = get_db().collection("waitlist").where(filter=FieldFilter("created_at", ">=", cutoff_iso)).stream()
    return [doc.to_dict() for doc in docs]


def get_mentors_since(cutoff_iso: str) -> list[dict]:
    docs = get_db().collection("mentors").where(filter=FieldFilter("created_at", ">=", cutoff_iso)).stream()
    return [doc.to_dict() for doc in docs]


def count_active_users() -> int:
    return sum(1 for _ in get_db().collection("users").stream())


def save_mentor(mentor_id: str, mentor: dict):
    get_db().collection("mentors").document(mentor_id).set(mentor)


def get_active_mentors() -> list[dict]:
    results = []
    for doc in get_db().collection("mentors").where(filter=FieldFilter("active", "==", True)).stream():
        data = doc.to_dict()
        data["id"] = doc.id
        results.append(data)
    return results


def get_mentor_by_id(mentor_id: str) -> dict | None:
    doc = get_db().collection("mentors").document(mentor_id).get()
    if doc.exists:
        data = doc.to_dict()
        data["id"] = doc.id
        return data
    return None


def get_mentor_by_token(token: str) -> tuple[str | None, dict | None]:
    docs = list(get_db().collection("mentors").where(filter=FieldFilter("opt_out_token", "==", token)).stream())
    if docs:
        return docs[0].id, docs[0].to_dict()
    return None, None


def optout_mentor(mentor_id: str):
    get_db().collection("mentors").document(mentor_id).update({"active": False})


def deactivate_mentor(mentor_id: str):
    get_db().collection("mentors").document(mentor_id).update({"active": False})


def reactivate_mentor(mentor_id: str):
    get_db().collection("mentors").document(mentor_id).update({"active": True})


def delete_mentor(mentor_id: str):
    get_db().collection("mentors").document(mentor_id).delete()


def update_mentor(mentor_id: str, updates: dict):
    get_db().collection("mentors").document(mentor_id).update(updates)


def get_mentor_by_email(email: str) -> tuple[str | None, dict | None]:
    docs = list(get_db().collection("mentors").where(filter=FieldFilter("email", "==", email.lower())).stream())
    if docs:
        return docs[0].id, docs[0].to_dict()
    return None, None
