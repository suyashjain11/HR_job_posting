HR ATS App (FastAPI)
AI-powered HR portal and candidate application system. Create shareable apply links, collect PDF resumes (kept with original filenames), run ATS scoring via Google Generative AI, review applicants in a clean HR dashboard, open full details in a modal, accept/reject with SMTP emails, and export to Excel — all self-hosted and lightweight.

Features
HR dashboard to create jobs and share apply links

Candidate page with PDF upload and server-side validation

ATS analysis (match %, missing keywords, profile summary)

Applicants table: Date, Name, ATS score, Email, Details modal

Details modal: full profile, resume download, Accept/Reject + email

Resumes saved using the candidate’s original filename (unique-prefixed on collisions)

Excel export of applicants with readable summaries

SMTP notifications (Accept/Reject) using configurable templates

Diagnostics endpoint to verify SMTP configuration

Tech Stack
FastAPI for the backend

Vanilla HTML/CSS/JS for HR and Candidate UIs

Google Generative AI for ATS scoring

PyPDF2 for resume parsing

pandas + openpyxl for Excel export

SMTP for email delivery

Getting Started
Prerequisites
Python 3.10+

A Google Generative AI API key

SMTP credentials (Gmail App Password or equivalent)

Setup
Clone and enter the project directory

git clone https://github.com/your-username/your-repo.git

cd your-repo

Create and activate a virtual environment

python -m venv .venv

On Windows: .venv\Scripts\activate

On macOS/Linux: source .venv/bin/activate

Install dependencies

pip install -r requirements.txt

Configure environment

Copy .env.example to .env

Fill in:

GOOGLE_API_KEY

SMTP_HOST, SMTP_PORT, SMTP_USE_SSL, SMTP_USER, SMTP_PASS, SMTP_FROM, SMTP_FROM_NAME

COMPANY_NAME (used in email templates)

Example (Gmail with App Password):

SMTP_HOST=smtp.gmail.com

SMTP_PORT=465

SMTP_USE_SSL=true

SMTP_USER=you@gmail.com

SMTP_PASS=your_16_char_app_password

SMTP_FROM=you@gmail.com

SMTP_FROM_NAME=HR Team

Run the app

python -m uvicorn hr_ats_app:app --reload

Open the HR portal

http://127.0.0.1:8000/hr

Usage
HR Flow
Create a job with a designation and JD.

Copy the generated apply link and share it.

Use the “Load Applicants” button with the job token to review submissions.

Click “Details” for full info, resume download, and Accept/Reject (email sent automatically if SMTP is configured).

Download Excel anytime from the dashboard.

Candidate Flow
Visit the apply link (includes job token).

Fill details, upload a PDF resume, and submit.

The resume is validated server-side; ATS analysis runs and the application is stored.

Email Templates (no ATS content included)
Accepted — Subject: “Congratulations! Your Application Has Been Accepted”

Rejected — Subject: “Update on Your Application”

Bodies are configurable in code; they interpolate candidate name and job designation, and use COMPANY_NAME from .env.

File Storage
Resumes are saved to resumes/ using the original uploaded filename. If a file with that name exists, a short UUID prefix is added to avoid collisions.

Helpful Endpoints
HR UI: /hr

Candidate UI: /apply/{token}

Applicants (JSON): /hr/applicants/{token}

Update status: /hr/update_status/{token}/{email}

Export Excel: /hr/download_excel

Download resume: /hr/download_resume/{filename}

SMTP status (diagnostics): /hr/smtp_status

Project Structure (high level)
hr_ats_app.py — FastAPI app, endpoints, ATS, email, Excel

static/

hr.html — HR dashboard

candidate.html — Candidate page

resumes/ — Saved resumes (created at runtime)

applicants.json / tokens.json — App data (created at runtime)

requirements.txt — Dependencies

.env.example — Environment template

README.md — This file

Security & Privacy
Never commit .env or real credentials. .gitignore excludes .env, resumes, and generated files.

Rotate API keys and SMTP passwords if shared or leaked.

PDFs are parsed server-side; only PDFs are accepted.

Troubleshooting
SMTP not sending: verify SMTP_* variables in .env, restart the server, and check /hr/smtp_status.

Port/SSL pair:

465 → SMTP_USE_SSL=true

587 → SMTP_USE_SSL=false (uses STARTTLS)

ATS errors: confirm GOOGLE_API_KEY and model availability.

File upload rejections: ensure the file is a valid, readable PDF.

License
MIT (or your preferred license)

Roadmap Ideas
Auth for HR portal

Multi-job dashboards and filters

Database backend (Postgres) with ORM

S3/GCS resume storage options

Webhook integrations for notifications and HRIS systems
