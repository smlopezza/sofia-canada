import logging
from collections import Counter

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.firestore_client import get_all_contacts, get_all_users

router = APIRouter()
logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

STATE_LABELS = {
    "en": {
        "onboarding": "Getting to know SofIA",
        "first_contact_registered": "First contact registered",
        "first_chat_scheduled": "First chat scheduled",
        "first_chat_completed": "First chat completed",
        "building_momentum": "Building momentum",
        "deepening_relationships": "Deepening relationships",
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
        "interview_stage": "En proceso de entrevistas",
        "advancing_in_interviews": "Avanzando en entrevistas",
        "job_offer_received": "Oferta recibida",
        "job_landed": "¡Trabajo conseguido! 🎉",
        "first_90_days": "Primeros 90 días",
    },
}


def _build_stats(lang: str) -> dict:
    users = get_all_users()
    all_contacts = get_all_contacts()

    active_users = [u for u in users if u.last_active]
    total_contacts = len(all_contacts)
    total_chats = sum(len(c.chats) for _, _, c in all_contacts)
    chats_completed = sum(
        1 for _, _, c in all_contacts
        if any(chat.get("notes") for chat in c.chats)
    )

    countries = Counter(u.country_of_origin for u in active_users if u.country_of_origin)
    cities = Counter(u.city for u in active_users if u.city)
    languages = Counter(u.language for u in active_users if u.language)

    labels = STATE_LABELS.get(lang, STATE_LABELS["en"])
    journey = Counter(u.current_state for u in active_users if u.current_state)
    journey_display = [
        {"state": labels.get(state, state), "count": count}
        for state, count in sorted(journey.items(), key=lambda x: -x[1])
    ]

    return {
        "total_users": len(active_users),
        "total_contacts": total_contacts,
        "total_chats": total_chats,
        "chats_with_notes": chats_completed,
        "countries": dict(countries.most_common(10)),
        "cities": dict(cities.most_common(8)),
        "languages": dict(languages),
        "journey": journey_display,
    }


@router.get("/", response_class=HTMLResponse)
def home(request: Request, lang: str = "en"):
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
    })


@router.get("/impact", response_class=HTMLResponse)
def impact_redirect():
    return RedirectResponse(url="/")
