import logging
from collections import Counter

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.firestore_client import get_all_contacts, get_all_users

router = APIRouter()
logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/impact", response_class=HTMLResponse)
def impact_dashboard(request: Request):
    try:
        users = get_all_users()
        all_contacts = get_all_contacts()
    except Exception:
        logger.exception("Failed to load impact stats")
        return HTMLResponse("<p>Error loading stats.</p>", status_code=500)

    active_users = [u for u in users if u.last_active]
    total_contacts = len(all_contacts)
    total_chats = sum(len(c.chats) for _, _, c in all_contacts)
    chats_completed = sum(
        1 for _, _, c in all_contacts
        if any(chat.get("notes") for chat in c.chats)
    )

    countries = Counter(
        u.country_of_origin for u in active_users if u.country_of_origin
    )
    cities = Counter(u.city for u in active_users if u.city)
    languages = Counter(u.language for u in active_users if u.language)

    state_labels = {
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
    }
    journey = Counter(u.current_state for u in active_users if u.current_state)
    journey_display = [
        {"state": state_labels.get(state, state), "count": count}
        for state, count in sorted(journey.items(), key=lambda x: -x[1])
    ]

    stats = {
        "total_users": len(active_users),
        "total_contacts": total_contacts,
        "total_chats": total_chats,
        "chats_with_notes": chats_completed,
        "countries": dict(countries.most_common(10)),
        "cities": dict(cities.most_common(8)),
        "languages": dict(languages),
        "journey": journey_display,
    }

    return templates.TemplateResponse("impact.html", {
        "request": request,
        "stats": stats,
    })
