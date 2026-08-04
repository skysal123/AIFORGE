# AIForge Technologies

> From ideas to intelligent products.

A Flask + HTML/CSS/JS marketing site for AIForge Technologies — an AI
solutions studio offering custom AI, web development, AI integration,
training & mentorship, and AI Assistants-as-a-Service.

## Run locally

```bash
# Windows
C:\venv\AIFORGE\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open http://localhost:5000

## Project structure

```
app/
├── __init__.py          # create_app()
├── config.py            # env-driven config
├── extensions.py        # db, mail, csrf
├── models.py            # Enquiry
├── blueprints/main/     # routes (/, /services, /about, /contact, /thank-you)
├── templates/           # Jinja2 pages
├── static/              # css, js, images
└── utils/mail.py        # enquiry email helper
run.py                   # dev entry point
requirements.txt
.env.example
```

## Phase 1 deliverable

Static site with enquiry capture:
- Home, Services, About, Contact, Thank-you pages
- Sticky navbar + mobile menu
- Floating WhatsApp CTA
- Contact form posts to `/enquiry` → stored in SQLite + emailed (if SMTP set)
