# SofIA — Tu aliada en Canadá

A bilingual (English/Spanish) AI companion for Latino newcomers to Canada navigating their job transition. SofIA helps users understand why reaching out to other professionals matters, prepare for coffee chats, set career goals, and find regional newcomer resources — delivered conversationally over WhatsApp.

## What it does

- **WhatsApp-native conversation** — users chat with SofIA through their existing WhatsApp; no app to install
- **Bilingual** — responds naturally in English or Spanish, matching the user's language
- **Coffee chat coaching** — helps users prepare for and reflect on professional conversations
- **Contact tracking** — logs contacts, scheduled chats, and follow-ups in a structured profile
- **Progress & milestones** — tracks career journey stages from onboarding through job offer
- **Mentor directory** — connects users with volunteer mentors who can offer guidance
- **Web dashboard** — users can review their profile, contacts, and learnings via a web interface

## Tech stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Uvicorn |
| AI | Claude (Anthropic) via `anthropic` SDK |
| Messaging | Twilio (WhatsApp webhook) |
| Database | Google Cloud Firestore |
| Templates | Jinja2 |
| Email | Resend |
| Observability | Langfuse |
| Container | Docker |
| Cloud | Google Cloud Run |

## Project structure

```
app/
  clients/
    claude_client.py      # Anthropic API wrapper
    firestore_client.py   # Firestore read/write
    twilio_client.py      # WhatsApp message sending
    email_client.py       # Transactional email via Resend
  routers/
    webhook.py            # Incoming WhatsApp messages
    dashboard.py          # User activity dashboard
    profile.py            # Profile view and edit
    jobs.py               # Job listings
    mentors.py            # Mentor registration and profiles
    landing.py            # Public landing page
  prompts.py              # SofIA's system prompt and persona
  models.py               # Firestore data models
  utils.py                # Shared helpers
  main.py                 # FastAPI app and router registration
  templates/              # Jinja2 HTML templates
  static/                 # CSS and images
Dockerfile
requirements.txt
```

## Local development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables (copy and fill in)
cp .env.example .env

# Run locally
uvicorn app.main:app --reload --port 8080
```

Required environment variables:

```
ANTHROPIC_API_KEY=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_NUMBER=
GOOGLE_APPLICATION_CREDENTIALS=
RESEND_API_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
```

## Deployment

The app runs on Google Cloud Run. Build and deploy with:

```bash
gcloud builds submit --tag gcr.io/<PROJECT_ID>/sofia-canada
gcloud run deploy sofia-canada \
  --image gcr.io/<PROJECT_ID>/sofia-canada \
  --platform managed \
  --region northamerica-northeast1 \
  --allow-unauthenticated
```

The Twilio webhook should point to `https://<your-cloud-run-url>/webhook`.

## Evaluation

`run_judge_tests.py` runs LLM-as-judge evaluations against a test set to measure response quality across dimensions like directness, cultural accuracy, and bilingual fluency. Results are logged to `judge_results_*.json`.

## Constraints

- Does **not** replace a mentor or career coach
- Does **not** answer immigration questions (redirects to IRCC and government resources)
- Does **not** replace mental health support (routes to appropriate resources)

## Author

Built by [Sandra Lopez-Zamora](https://www.slopezza.com) as a portfolio project, developed during the [Aggregate Intellect - AI engineering Buildcamp](https://sherpa-b.ai.science/).
