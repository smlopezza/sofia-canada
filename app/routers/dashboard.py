import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.clients.firestore_client import get_active_mentors, get_all_contacts, get_all_users
from app.clients.twilio_client import get_client as get_twilio_client

router = APIRouter()
logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

STATE_LABELS = {
    "en": {
        "onboarding": "Getting to know SofIA",
        "first_contact_registered": "First contact registered",
        "first_chat_scheduled": "First chat scheduled",
        "first_chat_completed": "First chat completed",
        "building_momentum": "Building momentum",
        "deepening_relationships": "Deepening relationships",
        "mentor_identified": "Mentor identified ⭐",
        "interview_stage": "In interview process",
        "advancing_in_interviews": "Advancing in interviews",
        "job_offer_received": "Job offer received",
        "job_landed": "Job landed! 🎉",
        "first_90_days": "First 90 days",
    },
    "es": {
        "onboarding": "Conociendo a SofIA",
        "first_contact_registered": "Primer contacto registrado",
        "first_chat_scheduled": "Primer chat agendado",
        "first_chat_completed": "Primer chat completado",
        "building_momentum": "Construyendo momentum",
        "deepening_relationships": "Profundizando relaciones",
        "mentor_identified": "Mentor identificado ⭐",
        "interview_stage": "En proceso de entrevistas",
        "advancing_in_interviews": "Avanzando en entrevistas",
        "job_offer_received": "Oferta recibida",
        "job_landed": "¡Trabajo conseguido! 🎉",
        "first_90_days": "Primeros 90 días",
    },
}


def _parse_dt(val) -> datetime | None:
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(str(val))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def _in_window(val, threshold: datetime) -> bool:
    dt = _parse_dt(val)
    return dt is not None and dt >= threshold


def _get_twilio_costs() -> dict:
    try:
        client = get_twilio_client()
        last_month = sum(float(r.price or 0) for r in client.usage.records.last_month.list())
        last_year = sum(float(r.price or 0) for r in client.usage.records.last_year.list())
        return {"last_month": round(last_month, 2), "last_year": round(last_year, 2)}
    except Exception:
        logger.warning("Could not fetch Twilio costs")
        return {"last_month": None, "last_year": None}


def _build_stats(lang: str) -> dict:
    now = datetime.utcnow()
    one_month_ago = now - timedelta(days=30)
    one_year_ago = now - timedelta(days=365)

    date_ranges = {
        "year": f"{one_year_ago.strftime('%b %Y')} – {now.strftime('%b %Y')}",
        "month": f"{one_month_ago.strftime('%b %d')} – {now.strftime('%b %d, %Y')}",
    }

    users = get_all_users()
    all_contacts = get_all_contacts()

    # Users
    active_all = [u for u in users if u.last_active]
    active_year = [u for u in active_all if _in_window(u.last_active, one_year_ago)]
    active_month = [u for u in active_all if _in_window(u.last_active, one_month_ago)]

    # Contacts
    contacts_all = [(phone, cid, c) for phone, cid, c in all_contacts]
    contacts_year = [(p, i, c) for p, i, c in contacts_all if _in_window(c.created_at, one_year_ago)]
    contacts_month = [(p, i, c) for p, i, c in contacts_all if _in_window(c.created_at, one_month_ago)]

    # Mentors identified in conversations (is_mentor=True on contact docs)
    mentors_all = [(p, i, c) for p, i, c in contacts_all if c.is_mentor]
    mentors_year = [(p, i, c) for p, i, c in mentors_all if _in_window(c.created_at, one_year_ago)]
    mentors_month = [(p, i, c) for p, i, c in mentors_all if _in_window(c.created_at, one_month_ago)]

    # Volunteer mentors registered via the web form
    reg_mentors = get_active_mentors()
    reg_mentors_year = [m for m in reg_mentors if _in_window(m.get("created_at"), one_year_ago)]
    reg_mentors_month = [m for m in reg_mentors if _in_window(m.get("created_at"), one_month_ago)]

    # Coffee chats
    def count_chats(contact_list, threshold=None):
        count = 0
        for _, _, c in contact_list:
            for chat in c.chats:
                if threshold is None or _in_window(chat.get("scheduled_at"), threshold):
                    count += 1
        return count

    chats_all = count_chats(contacts_all)
    chats_year = count_chats(contacts_all, one_year_ago)
    chats_month = count_chats(contacts_all, one_month_ago)

    # Journey — state machine + derived mentor_identified step
    labels = STATE_LABELS.get(lang, STATE_LABELS["en"])
    journey_counter = Counter(u.current_state for u in active_all if u.current_state)
    mentor_users = sum(1 for u in active_all if u.mentor_count and u.mentor_count > 0)
    journey_display = []
    for state, count in sorted(journey_counter.items(), key=lambda x: -x[1]):
        journey_display.append({"state": labels.get(state, state), "count": count})
    if mentor_users:
        journey_display.append({"state": labels.get("mentor_identified"), "count": mentor_users})

    # Countries / cities
    countries = Counter(u.country_of_origin for u in active_all if u.country_of_origin)
    cities = Counter(u.city for u in active_all if u.city)
    user_languages = Counter(u.language for u in active_all if u.language)

    # Costs
    twilio_costs = _get_twilio_costs()
    costs = {
        "twilio": twilio_costs,
        "claude": {
            "last_month": os.getenv("CLAUDE_COST_LAST_MONTH"),
            "last_year": os.getenv("CLAUDE_COST_LAST_YEAR"),
        },
        "gcp": {
            "last_month": os.getenv("GCP_COST_LAST_MONTH"),
            "last_year": os.getenv("GCP_COST_LAST_YEAR"),
        },
    }

    def _total_cost(period):
        vals = [
            twilio_costs.get(period),
            _safe_float(os.getenv(f"CLAUDE_COST_{period.upper()}")),
            _safe_float(os.getenv(f"GCP_COST_{period.upper()}")),
        ]
        vals = [v for v in vals if v is not None]
        return round(sum(vals), 2) if vals else None

    # Community donations (Buy Me a Coffee — updated manually)
    donations = {
        "last_month": _safe_float(os.getenv("BMAC_LAST_MONTH")),
        "last_year": _safe_float(os.getenv("BMAC_LAST_YEAR")),
        "all_time": _safe_float(os.getenv("BMAC_TOTAL")),
    }

    def _net_cost(period):
        total = _total_cost(period)
        donated = donations.get(period)
        if total is None:
            return None
        return round(total - (donated or 0), 2)

    return {
        "users": {
            "all": len(active_all),
            "year": len(active_year),
            "month": len(active_month),
        },
        "contacts": {
            "all": len(contacts_all),
            "year": len(contacts_year),
            "month": len(contacts_month),
        },
        "volunteer_mentors": {
            "all": len(reg_mentors),
            "year": len(reg_mentors_year),
            "month": len(reg_mentors_month),
        },
        "mentors": {
            "all": len(mentors_all),
            "year": len(mentors_year),
            "month": len(mentors_month),
        },
        "chats": {
            "all": chats_all,
            "year": chats_year,
            "month": chats_month,
        },
        "journey": journey_display,
        "countries": dict(countries.most_common(10)),
        "cities": dict(cities.most_common(8)),
        "languages": dict(user_languages),
        "costs": costs,
        "total_cost": {
            "last_month": _total_cost("last_month"),
            "last_year": _total_cost("last_year"),
        },
        "donations": donations,
        "net_cost": {
            "last_month": _net_cost("last_month"),
            "last_year": _net_cost("last_year"),
        },
        "date_ranges": date_ranges,
    }


def _safe_float(val) -> float | None:
    try:
        return float(val) if val else None
    except (ValueError, TypeError):
        return None


@router.get("/impact", response_class=HTMLResponse)
def impact(request: Request, lang: str = "en"):
    lang = lang if lang in ("en", "es") else "en"
    try:
        stats = _build_stats(lang)
    except Exception:
        logger.exception("Failed to load impact stats")
        return HTMLResponse("<p>Error loading stats.</p>", status_code=500)

    return templates.TemplateResponse("impact.html", {
        "request": request,
        "stats": stats,
        "lang": lang,
        "date_ranges": stats.get("date_ranges", {}),
    })
