"""
End-to-end conversation test for SofIA.

Uses real Claude + Firestore but intercepts Twilio so replies print to terminal.
Each run gets a unique fake phone number — no cleanup needed between runs.

Usage:
    python test_e2e.py
    python test_e2e.py r9     # R9 framing check (scans for "networking" in early states)
    python test_e2e.py r21    # Resume/CV redirect — hard boundary + resource redirect
    python test_e2e.py r22    # T22 favor pena — warm contacts, can't make the ask
    python test_e2e.py r23    # Advice application loop — close the loop coaching
    python test_e2e.py p9     # All P9-derived scenarios (r21 + r22 + r23)
"""

import sys
import uuid
from unittest.mock import patch
from dotenv import load_dotenv

load_dotenv()

from app.routers.webhook import _process
from app.clients.firestore_client import save_user
from app.models import UserDoc

SEPARATOR = "-" * 60


def chat(phone: str, text: str, replies: list[str]) -> str | None:
    """Send one message, capture SofIA's reply, return it."""
    message_sid = str(uuid.uuid4())
    captured = []

    def capture(to_phone, body):
        captured.append(body)

    with patch("app.routers.webhook.send_message", side_effect=capture):
        _process(phone, text, message_sid)

    reply = captured[0] if captured else None
    if reply:
        replies.append(reply)
    return reply


def run_scenario(name: str, messages: list[str]) -> tuple[str, list[str]]:
    phone = "+1555" + uuid.uuid4().hex[:7]
    save_user(UserDoc(phone=phone, tier="test"))
    replies = []

    print(f"\n{SEPARATOR}")
    print(f"SCENARIO: {name}")
    print(f"Phone:    {phone}")
    print(SEPARATOR)

    for msg in messages:
        print(f"\n👤  {msg}")
        reply = chat(phone, msg, replies)
        if reply:
            print(f"\n🤖  {reply}")
        else:
            print("\n🤖  [no reply — check logs]")

    return phone, replies


def check_resume_boundary(replies: list[str]):
    """Check that SofIA refuses resume review and provides a useful redirect."""
    print(f"\n{SEPARATOR}")
    print("RESUME BOUNDARY CHECK — must refuse review AND provide redirect")
    print(SEPARATOR)

    # Patterns that signal SofIA is OFFERING to review/edit — not just mentioning the word.
    # Use multi-word phrases to avoid matching refusal sentences like "No puedo revisar".
    violation_patterns = [
        "puedo revisar tu", "voy a revisar", "revisemos tu cv", "revisemos el cv",
        "te reviso el", "mejora tu cv", "mejoremos el cv", "mejorar tu cv",
        "te ayudo con tu cv", "ayudarte con el cv", "ayudarte con el résumé",
        "let me review your", "i can review your", "i'll review your",
        "i can help you improve your resume", "help you improve your resume",
        "edit your resume", "rewrite your resume", "let me take a look at your",
    ]
    resource_patterns = [
        "acces", "costi", "settlement", "asentamiento", "jobscan",
        "career service", "servicios de carrera", "college", "coach", "ymca",
    ]
    connection_redirect_patterns = [
        "relacion", "relación", "conexion", "conexión", "connection",
        "habla de ti", "speaks up", "quien conoce", "who knows",
        "red ", "network",
    ]

    flagged = []
    for i, reply in enumerate(replies):
        lower = reply.lower()
        for pattern in violation_patterns:
            if pattern in lower:
                flagged.append((i + 1, pattern, reply[:120]))
                break

    has_resource = any(
        any(p in r.lower() for p in resource_patterns) for r in replies
    )
    has_connection_redirect = any(
        any(p in r.lower() for p in connection_redirect_patterns) for r in replies
    )

    if flagged:
        for turn, pattern, snippet in flagged:
            print(f"  ❌ Turn {turn}: found '{pattern}' — '{snippet}...'")
    else:
        print("  ✅ No resume review offers detected")

    if has_resource:
        print("  ✅ Redirect includes specific resource (settlement org / tool / college)")
    else:
        print("  ⚠️  No specific resource referenced — redirect may be too vague")

    if has_connection_redirect:
        print("  ✅ Response pivots to connections as the higher-leverage path")
    else:
        print("  ⚠️  No connection pivot found — may be a dead-end redirect")


def check_r9(replies: list[str], early_cutoff: int = None):
    """Scan replies for 'networking' in early-state messages."""
    print(f"\n{SEPARATOR}")
    print("R9 CHECK — 'networking' must not appear in early states")
    print(SEPARATOR)

    flagged = []
    check_replies = replies[:early_cutoff] if early_cutoff else replies
    for i, reply in enumerate(check_replies):
        lower = reply.lower()
        if "networking" in lower or "red de contactos" in lower:
            flagged.append((i + 1, reply[:120]))

    if flagged:
        for turn, snippet in flagged:
            print(f"  ❌ Turn {turn}: '{snippet}...'")
    else:
        print("  ✅ 'networking' not found in scanned replies")


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

ONBOARDING_NO_CONTACTS = [
    "Hola",
    "Me llamo María. Soy ingeniera de software.",
    "Llegué hace 3 meses a Toronto",
    "Estoy enviando aplicaciones pero no recibo respuestas",
    "No tengo contactos profesionales en Canadá todavía",
    "Mi mayor reto es entender cómo funciona el mercado laboral aquí",
]

ONBOARDING_WITH_CONTACTS = [
    "Hi, my name is Carlos",
    "I'm a data analyst, been in Vancouver for 6 months",
    "I've been applying but mostly silence so far",
    "I do have a few contacts — a former colleague who moved here 2 years ago",
    "My biggest challenge is knowing how to reach out without feeling like a burden",
]

POST_CALL_REFLECTION = [
    "Hola",
    "Soy Ana, analista financiera, 4 meses en Toronto",
    "Ya tengo aplicaciones enviadas, tengo un contacto: Rodrigo, director de finanzas en Deloitte",
    "Acabo de tener una conversación con Rodrigo, fue bastante buena",
    "Hablamos como 45 minutos, me preguntó mucho sobre mi experiencia en México",
    "Sí ofreció presentarme a alguien de su equipo sin que yo se lo pidiera",
]

# R16 — Event follow-up paralysis
R16_TC01 = [
    "Hola",
    "Me llamo Valentina, soy data analyst de Colombia, llevo 4 meses en Toronto",
    "Sigo buscando trabajo en mi área, no tengo muchos contactos todavía",
    "La semana pasada fui a un evento de Women in AI en Toronto. Agregué a 8 personas en LinkedIn. Creo que estoy haciendo bien el networking. ¿Qué debería hacer ahora?",
]

R16_TC02 = [
    "Hola",
    "Soy Lucía, analista de datos de México, 3 meses en Toronto",
    "Estoy buscando trabajo en data science, he ido a algunos eventos",
    "He ido a 3 eventos en los últimos dos meses y tengo más de 20 nuevas conexiones en LinkedIn. Pero nadie me ha contactado. ¿Debería empezar a buscar más eventos o hay otra cosa que pueda hacer?",
]

R16_TC03 = [
    "Hola",
    "Me llamo Sofía, soy data scientist de Argentina, llegué hace 3 meses a Toronto",
    "Solo he usado LinkedIn y Indeed para buscar trabajo",
    "Llevo 3 meses en Canadá y no sé dónde conocer personas en mi campo. Solo he usado LinkedIn y Indeed. ¿Hay algún lugar donde pueda conocer gente de manera más natural?",
]

# R17 — Survival job shame
R17_TC01 = [
    "Hola",
    "Soy Carolina, vengo de Colombia, llevo 6 meses en Toronto",
    "Tengo experiencia en data science, tengo maestría",
    "Actualmente trabajo en un supermercado para pagar las cuentas pero eso no tiene nada que ver con data science. Prefiero no mencionarlo. ¿Podemos enfocarnos en cómo mejorar mi perfil de LinkedIn?",
]

R17_TC02 = [
    "Hola",
    "Soy Mariana, analista de datos de Colombia, 5 meses en Toronto",
    "Trabajo en retail mientras busco trabajo en mi área",
    "Tengo un coffee chat mañana y me da mucho miedo que me pregunten qué estoy haciendo ahora porque estoy trabajando en retail. No quiero que piensen que no soy profesional. ¿Cómo respondo esa pregunta?",
]

R17_TC03 = [
    "Hola",
    "Soy Andrea, especialista en recursos humanos de México, llevo 8 meses en Toronto",
    "Trabajo en Loblaw pero busco trabajo en HR",
    "Llevo 8 meses trabajando en Loblaw mientras busco trabajo en mi área (recursos humanos). He estado tratando de hacer networking en LinkedIn pero nadie responde. ¿Qué más puedo hacer?",
]

# R18 — Volunteering
R18_TC01 = [
    "Hola",
    "Soy Daniela, data scientist de Argentina, 4 meses en Toronto",
    "Estoy buscando trabajo en data science, no tengo experiencia canadiense",
    "Llevo 4 meses aplicando a trabajos de data science y haciendo outreach en LinkedIn pero no estoy teniendo resultados. No tengo experiencia canadiense en mi resume y tampoco tengo referencias aquí. ¿Qué más puedo hacer?",
]

R18_TC02 = [
    "Hola",
    "Soy Isabel, ingeniera de software de Venezuela, 2 meses en Toronto",
    "Estoy buscando trabajo pero me cuesta mucho el networking",
    "No puedo hacer cold outreach — me genera demasiada ansiedad escribirle a personas que no conozco. Ya lo intenté y no pude. Creo que el networking simplemente no es para mí. ¿Hay alguna otra forma?",
]

R18_TC03 = [
    "Hola",
    "Me llamo Patricia, analista de datos de Colombia, 5 meses en Toronto",
    "Sigo buscando trabajo en data science",
    "Me dijeron que haga voluntariado pero las organizaciones donde puedo ayudar no tienen nada que ver con data science. ¿De qué me sirve si los empleadores quieren experiencia en mi área?",
]

# R7 remaining — post-call depth
R7_TC02 = [
    "Hola",
    "Soy Laura, data scientist de Colombia, 5 meses en Toronto",
    "Acabo de tener un coffee chat con Marco, Senior Software Engineer en una fintech",
    "Post-call notes: Coffee chat con Marco, Senior Software Engineer en una fintech startup. 30 minutos. Respondió mis preguntas pero también me hizo tres preguntas sobre el agente que estoy construyendo — quería saber sobre el tech stack, por qué elegí GCP, y qué problema estoy resolviendo. Me pidió mi GitHub. Al final dijo: 'I'd love to hear how this develops.' No sé qué hacer ahora.",
]

R7_TC03 = [
    "Hola",
    "Soy Camila, analista de datos de Brasil, 6 meses en Toronto",
    "Tuve un coffee chat con Patricia, Data Science Manager en una aseguradora canadiense",
    "Post-call notes: Coffee chat con Patricia, Data Science Manager en una aseguradora canadiense. 40 minutos — se pasó del tiempo. Respondió mis preguntas y luego inesperadamente compartió que su primer año en Canadá fue muy difícil, que casi regresó a Brasil, y que desearía haber tenido a alguien que la guiara en el networking. Escuché pero no supe cómo responder. Se sintió como una conversación real.",
]

# R9 — Framing mismatch
R9_TC01 = [
    "Hola",
    "Me llamo Valeria, soy ingeniera de sistemas de México, 3 meses en Toronto",
    "Estoy buscando trabajo pero tengo una duda sobre el proceso",
    "No disfruto el networking. Se siente muy transaccional — como si estuviera siguiendo un guion. Preferiría que no fuera parte del proceso pero entiendo que es necesario. ¿Hay alguna forma de hacerlo que no se sienta tan forzado?",
]

# R11 re-tests — reciprocal benefit bar
R11_TC01_RETEST = [
    "Hola",
    "Soy Sandra, data scientist de Colombia, 4 meses en Toronto",
    "Estoy buscando trabajo en data science, acabo de encontrar un contacto en LinkedIn",
    "Ya encontré a Ana en LinkedIn. Quiero escribirle pero siento que la voy a molestar. No sé si tiene tiempo para hablar con alguien que no conoce. ¿Qué hago?",
]

R11_TC02_RETEST = [
    "Hola",
    "Me llamo Isabel, analista de datos de Colombia, 4 meses en Toronto",
    "Encontré a Daniela en LinkedIn — es data analyst en una fintech en Toronto, no la conozco para nada. Quiero escribirle pero no estoy acostumbrada a llegar a personas que no conozco. No soy extrovertida y esto me genera mucha ansiedad. ¿Cómo lo hago?",
]

# R12 — Academia to industry
R12_TC01 = [
    "Hola",
    "Me llamo Jenn, tengo un doctorado en ingeniería química, llevo 8 meses en Toronto",
    "Estoy buscando trabajo en industria pero me cuesta presentarme",
    "Tengo un doctorado en ingeniería química. Cuando me preguntan tell me about yourself en entrevistas no sé qué decir. Hablo de mi investigación y siento que no conecta. ¿Cómo me presento en la industria?",
]

R12_TC02 = [
    "Hola",
    "Soy Jenn, investigadora con doctorado en ingeniería química, buscando trabajo en industria en Toronto",
    "En las entrevistas me preguntan qué resultados logré. Mis resultados son publicaciones y presentaciones en conferencias. Eso no suena bien en industria. ¿Qué digo?",
]

# R13-TC02 — Isolation at breaking point
R13_TC02 = [
    "Hola",
    "Llevo 8 meses en Canadá y todavía no encuentro trabajo en mi área. He intentado todo lo que me dicen que funciona y no funciona. Me siento muy sola en esto y ya estoy por rendirme.",
]

# R14-TC01 — Relationship freeze
R14_TC01 = [
    "Hola",
    "Soy Lucia, analista financiera de Colombia, 5 meses en Toronto",
    "La semana pasada tuve un coffee chat con Roberto — me lo presentó un amigo. Fue buena conversación. Le mandé el email de agradecimiento. Pero no sé cómo seguir el contacto sin que se sienta forzado. ¿Qué hago?",
]

# R20 — Stage behavior and milestone celebrations
R20_TC01 = [
    "Hola",
    "Soy Valentina, data analyst de Colombia, 4 meses en Toronto",
    "Estoy buscando trabajo, encontré a Ana en LinkedIn y me ayudaste a escribirle",
    "¡Lo envié! Le mandé el mensaje a Ana. Me costó pero lo hice.",
]

R20_TC02 = [
    "Hola",
    "Soy Valentina, data analyst de Colombia, 4 meses en Toronto",
    "Hice outreach a Ana en LinkedIn la semana pasada",
    "¡Me respondió! Ana me respondió en LinkedIn y me dijo que le parece bien tener un café. No lo puedo creer.",
]

R20_TC03 = [
    "Hola",
    "Soy Valentina, data analyst de Colombia, 4 meses en Toronto",
    "Ana aceptó mi mensaje y quedamos en reunirnos",
    "¡Ya tenemos fecha! El café con Ana es el jueves a las 10am por Google Meet. ¿Cómo me preparo?",
]

R20_TC04 = [
    "Hola",
    "Soy Gabriela, ingeniera de software de Argentina, 8 meses en Toronto",
    "Ya tuve 3 coffee chats y creo que estoy entendiendo mejor cómo funciona esto del networking acá. ¿Cómo sé si lo estoy haciendo bien?",
]

R20_TC05 = [
    "Hola",
    "Soy Valentina, data analyst de Colombia, 4 meses en Toronto",
    "Tuve mi primer coffee chat con Ana la semana pasada, fue muy bien",
    "Ana me escribió y quiere volver a reunirse la próxima semana. Dice que quiere escuchar cómo me está yendo. ¿Es normal eso?",
]

R20_TC06 = [
    "Hola",
    "Soy Mariana, analista de datos de Colombia, llevo 7 meses buscando trabajo en Toronto",
    "¡Conseguí el trabajo! Me ofrecieron el puesto en TD y lo acepté. No puedo creer que finalmente lo logré.",
]

R20_TC07 = [
    "Hola",
    "Soy Jenn, tengo doctorado en ingeniería química, llevo 8 meses en Toronto buscando trabajo en industria. En las entrevistas no sé cómo responder tell me about yourself. ¿Cómo me presento?",
]

# R21 — Resume/CV redirect (hard boundary)
R21_TC01 = [
    "Hola",
    "Soy Camila, analista de datos de Colombia, 4 meses en Toronto",
    "Estoy buscando trabajo en data science",
    "¿Puedes revisar mi CV y decirme qué mejorar?",
]

R21_TC02 = [
    "Hi, I'm Marco, software engineer from Mexico, 5 months in Toronto",
    "I've been applying but not getting any responses",
    "Can you help me improve my resume? I think that's what's holding me back",
]

R21_TC03 = [
    "Hola",
    "Soy Elena, HR specialist de Venezuela, 3 meses en Toronto",
    "Voy a mandarte mi CV para que lo revises",
    "[Documento adjunto: Elena_CV_2026.pdf]",
]

R21_TC04 = [
    "Hola",
    "Soy Rafael, ingeniero de sistemas de México, 6 meses en Toronto",
    "Necesito ayuda con mi CV. Llevo meses aplicando y no recibo respuestas. Creo que el problema es el CV.",
    "Sí, ya sé que el networking importa, pero primero necesito que el CV esté bien. ¿No puedes solo revisarlo rápido?",
]

# R22 — T22 Favor pena: warm contact, can't make the ask
R22_TC01 = [
    "Hola",
    "Soy Valeria, analista de datos de Colombia, 3 meses en Toronto",
    "Tuve un coffee chat con Sandra hace dos semanas, fue muy bien",
    "Sandra me dijo que podía mandarle mi CV para que lo compartiera con su equipo. Pero me dio pena hacerlo. No quiero molestarla más.",
]

R22_TC02 = [
    "Hola",
    "Soy Isabella, ingeniera de software de Argentina, 4 meses en Toronto",
    "Ya tuve 5 coffee chats y todas fueron muy bien — la gente es muy receptiva aquí",
    "He tenido 5 buenas conversaciones pero no sé qué hacer con ellas. No quiero pedirles cosas. ¿Cómo paso al siguiente paso sin sentir que estoy molestando?",
]

R22_TC03 = [
    "Hola",
    "Me llamo Sofía, data scientist de México, llevo 2 meses en Toronto",
    "He tenido varios coffee chats y la gente ha sido muy amable",
    "Una persona me ofreció presentarme a alguien de su empresa pero me dio mucha pena aceptar. No quiero parecer insistente. ¿Qué hago?",
]

# R23 — Advice application loop
R23_TC01 = [
    "Hola",
    "Soy Natalia, analista financiera de Colombia, 5 meses en Toronto",
    "La semana pasada tuve un coffee chat con Roberto",
    "Apliqué lo que me dijo Roberto sobre cómo personalizar el mensaje en LinkedIn y funcionó — ya me respondieron dos personas. Pero no sé qué más hacer.",
]

R23_TC02 = [
    "Hola",
    "Soy Paula, data scientist de Brasil, 4 meses en Toronto",
    "Tuve un café con Ana hace tres semanas, me dio consejos sobre cómo hacer preguntas más estratégicas",
    "Le escribí a Ana para contarle cómo me fue con sus consejos. Respondió de inmediato, muy contenta, y me ofreció presentarme a alguien más. No esperaba eso.",
]

# R19 — First-years gap shame
R19_TC01 = [
    "Hola",
    "Me llamo Diana, soy contadora de Venezuela, llevo 2 años en Toronto",
    "Llevo 2 años en Canadá pero apenas estoy empezando a buscar trabajo en mi área (contabilidad). Los primeros dos años los pasé estudiando inglés y en programas de integración. Siento que perdí mucho tiempo y que debería estar más avanzada. ¿Por dónde empiezo?",
]

R19_TC02 = [
    "Hola",
    "Soy Fátima, ingeniera civil de Siria, llevo 3 años en Toronto",
    "Estoy buscando trabajo en ingeniería, tengo un coffee chat pronto",
    "Tengo 3 años en Canadá y estoy por tener mi primer coffee chat en mi área (ingeniería). Me preocupa que me pregunten qué he hecho estos años — los primeros dos los pasé en procesos de asentamiento y apoyando a mi familia. No sé cómo explicarlo sin que suene mal.",
]

MANUAL_E2E_DESPERATE_SWE = [
    "Hola",
    "Soy Diego, soy ingeniero de software, llevo 2 años en Canadá y no encuentro trabajo en mi área. Estoy desesperado.",
    "Tengo 8 años de experiencia como desarrollador backend en México. Aquí trabajo en un supermercado.",
    "He aplicado a cientos de trabajos y nada. Siento que mi experiencia de México no vale acá.",
    "Me da vergüenza decirle a la gente que trabajo en un supermercado. Cuando me preguntan qué hago acá no sé qué decir.",
    "Un amigo me dijo que debería hacer networking pero no sé por dónde empezar y honestamente no me siento capaz.",
]

NEW_SCENARIOS = [
    ("R16-TC01 — Event follow-up: attended Women in AI, added 8 LinkedIn", R16_TC01),
    ("R16-TC02 — Event follow-up: 3 events, 20+ connections, no messages", R16_TC02),
    ("R16-TC03 — Community discovery: 3 months, only LinkedIn/Indeed", R16_TC03),
    ("R17-TC01 — Survival job: wants to hide grocery store job", R17_TC01),
    ("R17-TC02 — Survival job: coffee chat tomorrow, scared of 'what do you do?'", R17_TC02),
    ("R17-TC03 — Survival job: 8 months at Loblaw, untapped network", R17_TC03),
    ("R18-TC01 — Volunteering: no Canadian experience, 4 months stuck", R18_TC01),
    ("R18-TC02 — Volunteering: cold outreach anxiety, wants alternative path", R18_TC02),
    ("R18-TC03 — Volunteering: thinks it only counts if in her field", R18_TC03),
]


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "onboarding"

    if mode == "r9":
        phone, replies = run_scenario(
            "R9 Framing — Spanish onboarding, no contacts",
            ONBOARDING_NO_CONTACTS,
        )
        check_r9(replies)

    elif mode == "contacts":
        run_scenario(
            "Onboarding — English, has contacts",
            ONBOARDING_WITH_CONTACTS,
        )

    elif mode == "reflection":
        run_scenario(
            "Post-call reflection — R7 Socratic check",
            POST_CALL_REFLECTION,
        )

    elif mode == "new":
        for name, messages in NEW_SCENARIOS:
            run_scenario(name, messages)

    elif mode.startswith("r16"):
        for name, messages in NEW_SCENARIOS[:3]:
            run_scenario(name, messages)

    elif mode.startswith("r17"):
        for name, messages in NEW_SCENARIOS[3:6]:
            run_scenario(name, messages)

    elif mode.startswith("r18"):
        for name, messages in NEW_SCENARIOS[6:]:
            run_scenario(name, messages)

    elif mode == "gaps":
        run_scenario("R7-TC02 — Post-call: Marco reciprocal curiosity + GitHub", R7_TC02)
        run_scenario("R7-TC03 — Post-call: Patricia personal self-disclosure", R7_TC03)
        run_scenario("R9-TC01 — Framing: networking feels transactional", R9_TC01)
        run_scenario("R11-TC01 retest — Fear of bothering: warm contact (Ana)", R11_TC01_RETEST)
        run_scenario("R11-TC02 retest — Introvert cold outreach (Daniela)", R11_TC02_RETEST)
        run_scenario("R12-TC01 — Academia: About Me paralysis", R12_TC01)
        run_scenario("R12-TC02 — Academia: impact articulation paralysis", R12_TC02)
        run_scenario("R13-TC02 — Human support: isolation at breaking point", R13_TC02)
        run_scenario("R14-TC01 — Relationship freeze after coffee chat", R14_TC01)

    elif mode == "manual":
        run_scenario(
            "MANUAL E2E — Diego, software engineer, 2 years in Canada, grocery store, desperate",
            MANUAL_E2E_DESPERATE_SWE,
        )

    elif mode.startswith("r20"):
        run_scenario("R20-TC01 — Milestone: first outreach sent", R20_TC01)
        run_scenario("R20-TC02 — Milestone: first reply received", R20_TC02)
        run_scenario("R20-TC03 — Milestone: first coffee chat scheduled", R20_TC03)
        run_scenario("R20-TC04 — Stage: building momentum language evolution", R20_TC04)
        run_scenario("R20-TC05 — Stage: deepening relationships mentor introduction", R20_TC05)
        run_scenario("R20-TC06 — Stage: job landed pay-it-forward", R20_TC06)
        run_scenario("R20-TC07 — Onboarding shortcut: full context upfront", R20_TC07)

    elif mode.startswith("r19"):
        run_scenario("R19-TC01 — First-years gap: 2 years in Canada, ESL/settlement, feels behind", R19_TC01)
        run_scenario("R19-TC02 — First-years gap: refugee context, coffee chat, afraid gap looks bad", R19_TC02)

    elif mode.startswith("r21"):
        _, r1 = run_scenario("R21-TC01 — Resume redirect: Spanish direct ask", R21_TC01)
        check_resume_boundary(r1)
        _, r2 = run_scenario("R21-TC02 — Resume redirect: English direct ask", R21_TC02)
        check_resume_boundary(r2)
        _, r3 = run_scenario("R21-TC03 — Resume redirect: document upload attempt", R21_TC03)
        check_resume_boundary(r3)
        _, r4 = run_scenario("R21-TC04 — Resume redirect: persistent user pushes back", R21_TC04)
        check_resume_boundary(r4)

    elif mode.startswith("r22"):
        run_scenario("R22-TC01 — Favor pena: warm contact offered to share CV, user held back", R22_TC01)
        run_scenario("R22-TC02 — Favor pena: 5 good coffee chats, no concrete asks", R22_TC02)
        run_scenario("R22-TC03 — Favor pena: offer of intro made, user too shy to accept", R22_TC03)

    elif mode.startswith("r23"):
        run_scenario("R23-TC01 — Advice loop: applied Roberto's advice, needs coaching to close loop", R23_TC01)
        run_scenario("R23-TC02 — Advice loop: closed the loop, unexpected offer came back", R23_TC02)

    elif mode == "p9":
        # All scenarios derived from P9 insights
        _, r1 = run_scenario("R21-TC01 — Resume redirect: Spanish direct ask", R21_TC01)
        check_resume_boundary(r1)
        _, r2 = run_scenario("R21-TC02 — Resume redirect: English direct ask", R21_TC02)
        check_resume_boundary(r2)
        _, r3 = run_scenario("R21-TC03 — Resume redirect: document upload attempt", R21_TC03)
        check_resume_boundary(r3)
        _, r4 = run_scenario("R21-TC04 — Resume redirect: persistent user pushes back", R21_TC04)
        check_resume_boundary(r4)
        run_scenario("R22-TC01 — Favor pena: warm contact offered to share CV, user held back", R22_TC01)
        run_scenario("R22-TC02 — Favor pena: 5 good coffee chats, no concrete asks", R22_TC02)
        run_scenario("R22-TC03 — Favor pena: offer of intro made, user too shy to accept", R22_TC03)
        run_scenario("R23-TC01 — Advice loop: applied Roberto's advice, needs coaching to close loop", R23_TC01)
        run_scenario("R23-TC02 — Advice loop: closed the loop, unexpected offer came back", R23_TC02)

    else:
        phone, replies = run_scenario(
            "Onboarding — Spanish, no contacts (default)",
            ONBOARDING_NO_CONTACTS,
        )
        check_r9(replies)

    print(f"\n{SEPARATOR}")
    print("Done. Check Firestore to verify user doc was written correctly.")
    print(SEPARATOR)
