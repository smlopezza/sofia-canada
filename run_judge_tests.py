"""
Run R1 (coffee chat prep) and R7 (post-call reflection) test cases through the
current SofIA prompt and score outputs using the LLM-as-judge rubric.

Usage:
    python run_judge_tests.py              # R1 coffee chat prep (default)
    python run_judge_tests.py --rubric r7  # R7 post-call reflection
    python run_judge_tests.py --rubric all # both rubrics
"""

import argparse
import json
import time
from dotenv import load_dotenv

load_dotenv()

import anthropic
from app.models import UserDoc, ContactDoc
from app.clients.claude_client import build_context, get_client
from app.prompts import build_system_prompt

# ---------------------------------------------------------------------------
# Test cases — R1 (coffee chat prep)
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "id": "R1-TC01",
        "description": "Maria VP — domain + cultural (Latino), VP level",
        "user": UserDoc(
            phone="+test01",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            time_in_canada="18 months",
            current_state="first_contact_registered",
            about_me="PhD in Chemical Engineering, transitioning to data science industry in Canada.",
        ),
        "contact": ContactDoc(
            name="Maria",
            role="VP of Data Science",
            company="Major Canadian bank",
            connection_context="Met at Women in Data Science event. Both Latina, both in data science, both made academia-to-industry transition. Maria originally from Mexico, transitioned 8 years ago.",
        ),
        "user_message": "Quiero prepararme para mi coffee chat con Maria. Es VP de Data Science en un banco canadiense. Es de México, también hizo la transición de academia a industria. La conocí en un evento de Women in Data Science. ¿Cómo me preparo?",
    },
    {
        "id": "R1-TC02",
        "description": "Carlos — 5-yr friendship + shared immigrant journey",
        "user": UserDoc(
            phone="+test02",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            time_in_canada="18 months",
            current_state="first_contact_registered",
        ),
        "contact": ContactDoc(
            name="Carlos",
            role="Senior Product Manager",
            company="Toronto tech startup",
            connection_context="Worked together in Bogotá 5 years ago, good friends, kept in touch. He moved to Canada 3 years ago. He works in product, user in data science.",
        ),
        "user_message": "Voy a reunirme con Carlos, un amigo de hace 5 años de Bogotá. Trabajamos juntos allá. Él lleva 3 años en Canadá, yo 18 meses. Él trabaja en product management, yo en data science. ¿Cómo me preparo?",
    },
    {
        "id": "R1-TC03",
        "description": "Ahmed — cross-sector domain overlap only, cold contact",
        "user": UserDoc(
            phone="+test03",
            name="Test User",
            field="Data Science / Financial Risk Analytics",
            country_of_origin="Colombia",
            language="es",
            time_in_canada="18 months",
            current_state="first_contact_registered",
        ),
        "contact": ContactDoc(
            name="Ahmed",
            role="Director of Analytics",
            company="Large Canadian hospital network",
            connection_context="Found on LinkedIn, no mutual connections, no prior interaction. Both work with data but in completely different sectors — he in healthcare, user in financial risk.",
        ),
        "user_message": "Quiero prepararme para hablar con Ahmed. Es Director de Analytics en una red de hospitales canadienses. Lo encontré en LinkedIn, no tenemos conexiones en común. Los dos trabajamos con datos pero en sectores muy distintos — él en healthcare, yo en riesgo financiero. ¿Cómo me preparo?",
    },
    {
        "id": "R1-TC04",
        "description": "Jin — cross-cultural immigrant (Korean-Canadian), different field",
        "user": UserDoc(
            phone="+test04",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            time_in_canada="18 months",
            current_state="first_contact_registered",
        ),
        "contact": ContactDoc(
            name="Jin",
            role="Engineering Manager",
            company="Vancouver fintech company",
            connection_context="Met through Newcomers in Tech LinkedIn group. Originally from South Korea, 6 years in Canada. Different fields (engineering vs data science), different cultural backgrounds.",
        ),
        "user_message": "Tengo un coffee chat con Jin. Es Engineering Manager en una fintech en Vancouver. Es de Corea del Sur, lleva 6 años en Canadá. Lo conocí en un grupo de LinkedIn de Newcomers in Tech. Trabajamos en campos distintos — él en ingeniería, yo en data science. ¿Cómo me preparo?",
    },
    {
        "id": "R1-TC05",
        "description": "Dr. Sarah — professor/supervisor, reference letter, domain + academic + mentorship",
        "user": UserDoc(
            phone="+test05",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            time_in_canada="18 months",
            current_state="first_contact_registered",
        ),
        "contact": ContactDoc(
            name="Dr. Sarah",
            role="Professor of Data Science",
            company="Western University",
            connection_context="Supervised the user's graduate certificate program last year and wrote a reference letter. Knows the user's work well. Same field, has industry connections.",
        ),
        "user_message": "Voy a reunirme con la Dra. Sarah. Ella supervisó mi certificado de posgrado el año pasado y me escribió una carta de recomendación — conoce muy bien mi trabajo. Es profesora de Data Science en Western y tiene contactos en industria. ¿Cómo me preparo?",
    },
    {
        "id": "R1-TC06",
        "description": "Lisa VP — cross-cultural immigrant (Chinese-Canadian), English-language request",
        "user": UserDoc(
            phone="+test06",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="en",
            time_in_canada="18 months",
            current_state="first_contact_registered",
        ),
        "contact": ContactDoc(
            name="Lisa",
            role="VP of Analytics",
            company="Canadian telecom",
            connection_context="LinkedIn cold outreach accepted. Originally from China, 14 years in Canada. Immigrant professional who navigated Canadian corporate culture. No shared cultural background with user, but both navigated Canada as immigrants.",
        ),
        "user_message": "I have a coffee chat with Lisa next week. She's VP of Analytics at a telecom company. She's originally from China, been in Canada 14 years. I reached out cold on LinkedIn. How should I prepare?",
    },
    {
        "id": "R1-TC07",
        "description": "Tom — event-only cold contact, no shared background or field",
        "user": UserDoc(
            phone="+test07",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            time_in_canada="18 months",
            current_state="first_contact_registered",
        ),
        "contact": ContactDoc(
            name="Tom",
            role="Marketing Director",
            company="Toronto startup",
            connection_context="Met briefly at a startup networking event last week. Canadian, no immigrant experience. Different field (marketing vs data science). Only connection is the event.",
        ),
        "user_message": "Tengo un coffee chat con Tom la próxima semana. Es Director de Marketing en una startup de Toronto. Lo conocí brevemente en un evento de startups la semana pasada. Es canadiense, trabaja en marketing — nada en común conmigo. ¿Cómo me preparo?",
    },
    {
        "id": "R1-TC08",
        "description": "Roberto — sparse profile, minimal context about contact",
        "user": UserDoc(
            phone="+test08",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            time_in_canada="18 months",
            current_state="first_contact_registered",
        ),
        "contact": ContactDoc(
            name="Roberto",
            role="Developer",
            company="Canadian tech company (name unknown)",
            connection_context="A mutual acquaintance is going to make the introduction. User has almost no information about Roberto — only that he works as a developer at some Canadian company. No LinkedIn profile reviewed.",
        ),
        "user_message": "Un conocido me va a conectar con Roberto. Solo sé que trabaja como developer en alguna empresa canadiense. No revisé su LinkedIn. ¿Cómo me preparo?",
    },
    {
        "id": "R1-TC09",
        "description": "Isabella — existing friendship overrides cultural + domain",
        "user": UserDoc(
            phone="+test09",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            time_in_canada="18 months",
            current_state="first_contact_registered",
        ),
        "contact": ContactDoc(
            name="Isabella",
            role="Data Analyst",
            company="Canadian retail chain",
            connection_context="Friends from undergrad in Bogotá, 7 years ago. She moved to Canada 4 years ago. Both Latina (she's Venezuelan), both in data science/analytics. Three overlap types: existing friendship, cultural/immigrant, domain.",
        ),
        "user_message": "Voy a reunirme con Isabella, una amiga de la universidad en Bogotá de hace 7 años. Lleva 4 años en Canadá, yo 18 meses. Las dos somos latinas, las dos trabajamos con datos. ¿Cómo me preparo?",
    },
    {
        "id": "R1-TC10",
        "description": "Wei — shared newcomer experience wins over event context, junior contact",
        "user": UserDoc(
            phone="+test10",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            time_in_canada="18 months",
            current_state="first_contact_registered",
        ),
        "contact": ContactDoc(
            name="Wei",
            role="Junior Data Analyst",
            company="Canadian financial services firm",
            connection_context="Met at Data Science TO meetup last month. Originally from China, 8 months in Canada — even more recent newcomer than the user. Both navigating job search as recent immigrants in data science.",
        ),
        "user_message": "Conocí a Wei en un meetup de Data Science TO el mes pasado. Es Junior Data Analyst en una empresa financiera. Es de China, lleva 8 meses en Canadá — llegó antes que yo pero los dos somos newcomers. ¿Cómo me preparo?",
    },
]

# ---------------------------------------------------------------------------
# R7 test cases — post-call reflection
# ---------------------------------------------------------------------------

R7_CASES = [
    {
        "id": "R7-TC01",
        "description": "Patricia — personal self-disclosure + time overrun",
        "user": UserDoc(
            phone="+r7test01",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            current_state="first_chat_completed",
        ),
        "contact": ContactDoc(
            name="Patricia",
            role="Data Science Manager",
            company="Canadian insurance company",
            connection_context="Coffee chat contact — first call.",
        ),
        "user_message": "Acabo de terminar mi coffee chat con Patricia. Estuvimos 40 minutos — se pasó del tiempo. Contestó mis preguntas y luego, inesperadamente, compartió que su primer año en Canadá fue muy difícil, que casi se regresó a Brasil, y que ojalá hubiera tenido a alguien que la guiara con esto. Yo escuché pero no supe qué decir.",
        "signals": ["time_overrun", "personal_self_disclosure"],
    },
    {
        "id": "R7-TC02",
        "description": "Marco — reciprocal curiosity + GitHub request",
        "user": UserDoc(
            phone="+r7test02",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            current_state="first_chat_completed",
        ),
        "contact": ContactDoc(
            name="Marco",
            role="Senior Software Engineer",
            company="Fintech startup",
            connection_context="Coffee chat contact — first call.",
        ),
        "user_message": "Hablé con Marco hoy. 30 minutos. Él respondió mis preguntas pero también me hizo tres preguntas sobre el agente que estoy construyendo — quería saber el tech stack, por qué elegí GCP, y qué problema estoy resolviendo. Me pidió mi GitHub. Al final dijo 'me encantaría escuchar cómo va esto.' No sé qué hacer ahora.",
        "signals": ["reciprocal_curiosity", "github_request", "forward_looking_statement"],
    },
    {
        "id": "R7-TC03",
        "description": "David VP — no depth signals (false positive test)",
        "user": UserDoc(
            phone="+r7test03",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            current_state="first_chat_completed",
        ),
        "contact": ContactDoc(
            name="David",
            role="VP of Engineering",
            company="Large Canadian bank",
            connection_context="Recruiter referral — cold contact.",
        ),
        "user_message": "Hablé con David, VP de Engineering en un banco canadiense. Fue muy profesional — contestó todas mis preguntas sobre la empresa y el equipo. Exactamente 30 minutos, se despidió cordialmente. No me preguntó nada sobre mí, no ofreció nada, no sugirió seguimiento. Buena información. No sé si debo mantener el contacto.",
        "signals": [],
    },
    {
        "id": "R7-TC04",
        "description": "Ana — unprompted introduction offer",
        "user": UserDoc(
            phone="+r7test04",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            current_state="first_chat_completed",
        ),
        "contact": ContactDoc(
            name="Ana",
            role="HR Director",
            company="Toronto tech company",
            connection_context="Coffee chat contact — first call.",
        ),
        "user_message": "Tuve mi coffee chat con Ana hoy, 35 minutos. Contestó todo sobre procesos de contratación. Al final ella dijo 'de hecho conozco a alguien en Shopify haciendo exactamente lo que describes — te la presento.' Yo no le pedí nada. Le dije gracias. Fue una buena llamada.",
        "signals": ["unprompted_offer"],
    },
    {
        "id": "R7-TC05",
        "description": "Valentina — vague notes, excavation test",
        "user": UserDoc(
            phone="+r7test05",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            current_state="first_chat_completed",
        ),
        "contact": ContactDoc(
            name="Valentina",
            role="Analytics Lead",
            company="Retail company",
            connection_context="Coffee chat contact — first call.",
        ),
        "user_message": "Tuve mi coffee chat con Valentina, 35 minutos. Fue una muy buena conversación. Fue muy útil. Me siento bien.",
        "signals": [],  # vague — excavation should trigger
    },
    {
        "id": "R7-TC06",
        "description": "Camila — three simultaneous signals (time overrun + unprompted offer + reciprocal curiosity)",
        "user": UserDoc(
            phone="+r7test06",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            current_state="first_chat_completed",
        ),
        "contact": ContactDoc(
            name="Camila",
            role="Data Science Lead",
            company="Canadian fintech",
            connection_context="Coffee chat contact — first call.",
        ),
        "user_message": "Acabo de hablar con Camila. Fueron 50 minutos — nos pasamos del tiempo acordado. Me preguntó sobre mi proyecto, quería ver el código, me hizo cuatro preguntas sobre mi enfoque técnico. Y al final dijo que tiene un colega buscando un data scientist y que me va a mandar su contacto esta semana. No le pedí nada de eso.",
        "signals": ["time_overrun", "reciprocal_curiosity", "unprompted_offer"],
    },
    {
        "id": "R7-TC07",
        "description": "James — English-language notes, single clear signal",
        "user": UserDoc(
            phone="+r7test07",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="en",
            current_state="first_chat_completed",
        ),
        "contact": ContactDoc(
            name="James",
            role="Senior Data Engineer",
            company="Toronto e-commerce company",
            connection_context="Coffee chat contact — first call via LinkedIn cold outreach.",
        ),
        "user_message": "Just finished my call with James. It was 35 minutes. He answered my questions and at the end said 'I'd love to see how your agent project develops — send me an update when you launch.' I wasn't expecting that.",
        "signals": ["forward_looking_statement"],
    },
    {
        "id": "R7-TC08",
        "description": "Sofia — emotional framing, anxiety dominates notes, minimal detail",
        "user": UserDoc(
            phone="+r7test08",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            current_state="first_chat_completed",
        ),
        "contact": ContactDoc(
            name="Sofia",
            role="Analytics Manager",
            company="Canadian insurance company",
            connection_context="Coffee chat contact — first call.",
        ),
        "user_message": "Hablé con Sofia. Me fue bien pero estaba tan nerviosa que no recuerdo bien los detalles de la conversación. Siento que no expliqué bien mi experiencia. Creo que no causé buena impresión. No sé cómo fue realmente.",
        "signals": [],  # emotional framing — no signals identifiable, excavation needed
    },
    {
        "id": "R7-TC09",
        "description": "Miguel — minimal two-sentence notes, one clear strong signal",
        "user": UserDoc(
            phone="+r7test09",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            current_state="first_chat_completed",
        ),
        "contact": ContactDoc(
            name="Miguel",
            role="Head of Data",
            company="Canadian media company",
            connection_context="Coffee chat contact — first call via mutual introduction.",
        ),
        "user_message": "Hablé con Miguel. 30 minutos. Al final me dio su número de celular y me dijo que le escribiera directo si necesito algo.",
        "signals": ["unprompted_offer"],  # personal number + direct access = strong unprompted offer
    },
    {
        "id": "R7-TC10",
        "description": "Patricia — second conversation, relationship established, new unprompted offer",
        "user": UserDoc(
            phone="+r7test10",
            name="Test User",
            field="Data Science",
            country_of_origin="Colombia",
            language="es",
            current_state="first_chat_completed",
        ),
        "contact": ContactDoc(
            name="Patricia",
            role="Data Science Manager",
            company="Canadian insurance company",
            connection_context="Second conversation — had first coffee chat two weeks ago where she shared her difficult first year in Canada. Relationship already has depth.",
        ),
        "user_message": "Tuve mi segunda llamada con Patricia — la que me contó que su primer año en Canadá fue muy difícil. Esta vez me preguntó cómo voy con mi búsqueda, y antes de que yo pidiera nada, ofreció revisar mi perfil de LinkedIn y darme feedback esta semana. No lo esperaba.",
        "signals": ["unprompted_offer", "reciprocal_curiosity"],
    },
]

# ---------------------------------------------------------------------------
# Judge prompt (trimmed for scoring only)
# ---------------------------------------------------------------------------

JUDGE_SYSTEM = """You are an evaluation judge for the SofIA Conversation Agent.
Score the coffee chat prep output on 4 dimensions (1-5 scale):

D1 CONTACT PROFILE GROUNDING: Are questions rooted in the CONTACT's profile, not the user's background?
- 5: Every question could only have been written with this contact's profile. None project the user's expertise onto the contact.
- 3: Mix of contact-specific and generic/projected questions.
- 1: Questions reflect the user's background or a generic template. Contact profile absent.

D2 CONNECTION TYPE + RATIONALE: Did SofIA choose the right angle, name it, and commit to it?
Hierarchy: Existing relationship > Cultural/immigrant experience (cross-cultural counts) > Shared professional journey > Domain overlap > Event/context.
At Director+, domain is table stakes — cultural/immigrant wins.
- 5: Correct angle named with rationale. ALL questions flow from that angle only.
- 3: Correct angle but blended with others, or rationale absent.
- 1: Wrong angle, or no identifiable angle.

D3 CULTURAL WHY DEPTH: Does it teach the cultural reasoning, not just instructions?
- 5: Every key recommendation explains WHY it works in Canadian professional culture.
- 3: WHY present for some, absent for others.
- 1: Instructions only. No cultural reasoning.

D4 WHATSAPP CONCISENESS: Is it appropriately sized for WhatsApp?
- 5: Under ~500 words, purposeful, no markdown headers or bold markers.
- 3: Noticeably verbose, could cut 30%+.
- 1: Excessive, reads like a document.

Respond ONLY with valid JSON:
{
  "d1_contact_grounding": {"score": 0, "reasoning": ""},
  "d2_connection_type": {"score": 0, "reasoning": "", "failed_pillar": ""},
  "d3_cultural_why": {"score": 0, "reasoning": "", "failed_pillar": ""},
  "d4_conciseness": {"score": 0, "reasoning": ""},
  "requires_human_review": false,
  "overall_assessment": ""
}"""


JUDGE_R7_SYSTEM = """You are an evaluation judge for the SofIA Conversation Agent.
Score the post-call reflection output on 4 dimensions (1-5 scale):

D1 DEPTH SIGNAL RECOGNITION: Did SofIA correctly identify signals present — or their absence?
Signals: unprompted offer, reciprocal curiosity (they asked YOU questions), personal self-disclosure,
time overrun, forward-looking statement ("I'd love to hear how this develops").
ABSENCE matters: a VP who gave 30 professional minutes with no engagement is NOT a depth signal.
Seniority is not a depth signal.
- 5: Every signal named correctly. Absence correctly identified. No false positives.
- 3: Some signals caught, one missed. OR one false positive (seniority treated as signal).
- 1: Signals missed entirely. OR clear false positive — recommending follow-up on a no-signal call.

D2 SOCRATIC QUALITY: Did SofIA ask questions, not declare conclusions?
- 5: Pure open questions. Never states "this person has mentor potential." User arrives at insight themselves.
- 3: Mix of questions and declarations. User told what to think about some signals.
- 1: Fully declarative — tells user what the relationship means and what to do next.

D3 CONVERSATION SPECIFICITY: Grounded in THIS specific conversation?
Special case: vague notes ("fue buena conversación") should trigger excavation questions — output
will be generic but that is CORRECT behavior (score ceiling = 3, not a failure).
- 5: Every prompt references something specific from this conversation.
- 3: Mix of specific and generic. OR correct excavation on vague input (ceiling applies).
- 1: Fully generic. Same prompts for any post-call scenario.

D4 WHATSAPP CONCISENESS: Reflection before logistics, appropriately short.
- 5: Under ~200 words. Reflection prompts first. Logistics (thank-you, second meeting) only after reflection done, if at all.
- 3: Jumps to logistics before reflection is complete. OR verbose.
- 1: Skips reflection entirely — only logistics output (email template, follow-up message).

Respond ONLY with valid JSON:
{
  "d1_signal_recognition": {"score": 0, "signals_in_input": [], "signals_caught": [], "false_positives": [], "reasoning": ""},
  "d2_socratic_quality": {"score": 0, "reasoning": ""},
  "d3_specificity": {"score": 0, "vague_input_applied": false, "reasoning": ""},
  "d4_conciseness": {"score": 0, "reasoning": ""},
  "requires_human_review": false,
  "overall_assessment": ""
}"""


def run_sofia(user, contact, user_message):
    """Run SofIA's current prompt against a test input."""
    system = build_system_prompt(user)
    context = build_context(user, contact)
    messages = [{"role": "user", "content": f"{context}\n\n{user_message}"}]

    t0 = time.perf_counter()
    response = get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=messages,
    )
    elapsed = round(time.perf_counter() - t0, 2)
    output = response.content[0].text if response.content else ""
    # Strip <update> blocks — not part of the user-facing output
    import re
    output = re.sub(r'<update>.*?</update>', '', output, flags=re.DOTALL).strip()
    return output, elapsed


def judge_output(sofia_output, test_case):
    """Score a SofIA output using the judge rubric."""
    judge_input = f"""Test case: {test_case['id']} — {test_case['description']}

Contact profile:
- Name: {test_case['contact'].name}
- Role: {test_case['contact'].role} at {test_case['contact'].company}
- Connection context: {test_case['contact'].connection_context}

User field: {test_case['user'].field}
User country of origin: {test_case['user'].country_of_origin}

SofIA output to evaluate:
{sofia_output}"""

    response = get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": judge_input}],
    )
    raw = response.content[0].text if response.content else "{}"
    # Extract JSON
    import re
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if m:
        return json.loads(m.group())
    return {}


def judge_r7(sofia_output, test_case):
    """Score a post-call reflection output using Rubric 2."""
    judge_input = f"""Test case: {test_case['id']} — {test_case['description']}
Depth signals present in input: {test_case.get('signals', [])}

Contact: {test_case['contact'].name} ({test_case['contact'].role} at {test_case['contact'].company})
User post-call message: {test_case['user_message']}

SofIA output to evaluate:
{sofia_output}"""

    response = get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=JUDGE_R7_SYSTEM,
        messages=[{"role": "user", "content": judge_input}],
    )
    raw = response.content[0].text if response.content else "{}"
    import re
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if m:
        return json.loads(m.group())
    return {}


def run_r1():
    results = []
    print(f"\n{'='*70}")
    print("Running R1 — Coffee Chat Prep")
    print(f"{'='*70}\n")

    for tc in TEST_CASES:
        print(f"[{tc['id']}] {tc['description']}")
        sofia_output, latency = run_sofia(tc["user"], tc["contact"], tc["user_message"])
        print(f"  ✓ {latency}s ({len(sofia_output.split())} words)")

        scores = judge_output(sofia_output, tc)
        d1 = scores.get("d1_contact_grounding", {})
        d2 = scores.get("d2_connection_type", {})
        d3 = scores.get("d3_cultural_why", {})
        d4 = scores.get("d4_conciseness", {})
        avg = round((d1.get("score", 0) + d2.get("score", 0) + d3.get("score", 0) + d4.get("score", 0)) / 4, 2)
        review = scores.get("requires_human_review", False)
        print(f"  SCORES: D1={d1.get('score')} D2={d2.get('score')} D3={d3.get('score')} D4={d4.get('score')} → avg {avg} | review={'YES' if review else 'no'}")
        print(f"  D2: {d2.get('reasoning', '')[:120]}\n")

        results.append({"id": tc["id"], "description": tc["description"],
                        "sofia_output": sofia_output, "latency_s": latency, "scores": scores, "avg": avg})

    _print_r1_summary(results)
    with open("judge_results_r1_current.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nFull results → judge_results_r1_current.json")


def run_r7():
    results = []
    print(f"\n{'='*70}")
    print("Running R7 — Post-Call Reflection")
    print(f"{'='*70}\n")

    for tc in R7_CASES:
        print(f"[{tc['id']}] {tc['description']}")
        sofia_output, latency = run_sofia(tc["user"], tc["contact"], tc["user_message"])
        print(f"  ✓ {latency}s ({len(sofia_output.split())} words)")
        print(f"  SofIA: {sofia_output[:200]}{'...' if len(sofia_output) > 200 else ''}")

        scores = judge_r7(sofia_output, tc)
        d1 = scores.get("d1_signal_recognition", {})
        d2 = scores.get("d2_socratic_quality", {})
        d3 = scores.get("d3_specificity", {})
        d4 = scores.get("d4_conciseness", {})
        avg = round((d1.get("score", 0) + d2.get("score", 0) + d3.get("score", 0) + d4.get("score", 0)) / 4, 2)
        review = scores.get("requires_human_review", False)
        print(f"  SCORES: D1={d1.get('score')} D2={d2.get('score')} D3={d3.get('score')} D4={d4.get('score')} → avg {avg} | review={'YES' if review else 'no'}")
        print(f"  D1 caught: {d1.get('signals_caught', [])} | false+: {d1.get('false_positives', [])}")
        print(f"  Overall: {scores.get('overall_assessment', '')[:150]}\n")

        results.append({"id": tc["id"], "description": tc["description"],
                        "signals_expected": tc.get("signals", []),
                        "sofia_output": sofia_output, "latency_s": latency, "scores": scores, "avg": avg})

    print(f"{'='*70}")
    print(f"{'ID':<12} {'D1':>4} {'D2':>4} {'D3':>4} {'D4':>4} {'Avg':>6}  Review  Description")
    print(f"{'─'*70}")
    d1s, d2s, d3s, d4s = [], [], [], []
    for r in results:
        s = r["scores"]
        d1 = s.get("d1_signal_recognition", {}).get("score", 0)
        d2 = s.get("d2_socratic_quality", {}).get("score", 0)
        d3 = s.get("d3_specificity", {}).get("score", 0)
        d4 = s.get("d4_conciseness", {}).get("score", 0)
        d1s.append(d1); d2s.append(d2); d3s.append(d3); d4s.append(d4)
        rev = "YES" if s.get("requires_human_review") else "no"
        print(f"{r['id']:<12} {d1:>4} {d2:>4} {d3:>4} {d4:>4} {r['avg']:>6}  {rev:<6}  {r['description'][:35]}")
    print(f"{'─'*70}")
    if d1s:
        print(f"{'Average':<12} {sum(d1s)/len(d1s):>4.1f} {sum(d2s)/len(d2s):>4.1f} {sum(d3s)/len(d3s):>4.1f} {sum(d4s)/len(d4s):>4.1f}")

    with open("judge_results_r7_current.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nFull results → judge_results_r7_current.json")


def _print_r1_summary(results):
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"{'ID':<12} {'D1':>4} {'D2':>4} {'D3':>4} {'D4':>4} {'Avg':>6}  Review  Description")
    print(f"{'─'*70}")
    d1s, d2s, d3s, d4s = [], [], [], []
    for r in results:
        s = r["scores"]
        d1 = s.get("d1_contact_grounding", {}).get("score", 0)
        d2 = s.get("d2_connection_type", {}).get("score", 0)
        d3 = s.get("d3_cultural_why", {}).get("score", 0)
        d4 = s.get("d4_conciseness", {}).get("score", 0)
        d1s.append(d1); d2s.append(d2); d3s.append(d3); d4s.append(d4)
        rev = "YES" if s.get("requires_human_review") else "no"
        print(f"{r['id']:<12} {d1:>4} {d2:>4} {d3:>4} {d4:>4} {r['avg']:>6}  {rev:<6}  {r['description'][:35]}")
    print(f"{'─'*70}")
    if d1s:
        print(f"{'Average':<12} {sum(d1s)/len(d1s):>4.1f} {sum(d2s)/len(d2s):>4.1f} {sum(d3s)/len(d3s):>4.1f} {sum(d4s)/len(d4s):>4.1f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rubric", choices=["r1", "r7", "all"], default="r1",
                        help="Which rubric to run (default: r1)")
    args = parser.parse_args()

    if args.rubric in ("r1", "all"):
        run_r1()
    if args.rubric in ("r7", "all"):
        run_r7()


if __name__ == "__main__":
    main()
