"""
Run R1 coffee chat prep test cases through the current SofIA prompt
and score outputs using the LLM-as-judge rubric.

Usage:
    python run_judge_tests.py
"""

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
- 5: Under ~300 words, purposeful, no padding.
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


def main():
    results = []
    print(f"\n{'='*70}")
    print("Running R1 test cases through current SofIA prompt")
    print(f"{'='*70}\n")

    for tc in TEST_CASES:
        print(f"[{tc['id']}] {tc['description']}")
        print(f"  Running SofIA...")

        sofia_output, latency = run_sofia(tc["user"], tc["contact"], tc["user_message"])
        print(f"  ✓ Response in {latency}s ({len(sofia_output.split())} words)")
        print(f"\n  SofIA said:\n{'─'*50}")
        print(sofia_output[:800] + ("..." if len(sofia_output) > 800 else ""))
        print(f"{'─'*50}")

        print(f"  Judging...")
        scores = judge_output(sofia_output, tc)

        d1 = scores.get("d1_contact_grounding", {})
        d2 = scores.get("d2_connection_type", {})
        d3 = scores.get("d3_cultural_why", {})
        d4 = scores.get("d4_conciseness", {})
        avg = round((d1.get("score", 0) + d2.get("score", 0) + d3.get("score", 0) + d4.get("score", 0)) / 4, 2)
        review = scores.get("requires_human_review", False)

        print(f"\n  SCORES: D1={d1.get('score')} D2={d2.get('score')} D3={d3.get('score')} D4={d4.get('score')} → avg {avg} | review={'YES' if review else 'no'}")
        print(f"  D2 reasoning: {d2.get('reasoning', '')[:120]}")
        print(f"  Overall: {scores.get('overall_assessment', '')[:150]}")
        print(f"  Latency: {latency}s\n")

        results.append({
            "id": tc["id"],
            "description": tc["description"],
            "sofia_output": sofia_output,
            "latency_s": latency,
            "scores": scores,
            "avg": avg,
        })

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
    print(f"{'Average':<12} {sum(d1s)/len(d1s):>4.1f} {sum(d2s)/len(d2s):>4.1f} {sum(d3s)/len(d3s):>4.1f} {sum(d4s)/len(d4s):>4.1f}")

    # Save full results
    with open("judge_results_r1_current.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nFull results saved to judge_results_r1_current.json")


if __name__ == "__main__":
    main()
