from fastapi import FastAPI, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uuid, json, os, re, traceback, datetime
import google.generativeai as genai
from dotenv import load_dotenv
import PyPDF2 as pdf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from io import BytesIO

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

TOKENS_FILE = "tokens.json"
APPLICANTS_FILE = "applicants.json"
EXCEL_FILE = "applicants.xlsx"
RESUME_DIR = "resumes"
os.makedirs(RESUME_DIR, exist_ok=True)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "true").lower() == "true"
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "HR Team")

# --------- Data store ---------
if os.path.exists(TOKENS_FILE):
    with open(TOKENS_FILE, "r", encoding="utf-8") as f:
        TOKENS = json.load(f)
else:
    TOKENS = {}

if os.path.exists(APPLICANTS_FILE):
    with open(APPLICANTS_FILE, "r", encoding="utf-8") as f:
        APPLICANTS = json.load(f)
else:
    APPLICANTS = {}

# --------- Helpers ---------
def save_tokens():
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(TOKENS, f, indent=2)

def _clean_text(val):
    if val is None:
        return ""
    if not isinstance(val, str):
        val = str(val)
    val = val.replace("```", "").replace("`", "")
    val = re.sub(r"^\s*json\s*", "", val.strip(), flags=re.IGNORECASE)
    return val.strip()

def _sanitize_ats(ats_raw):
    if ats_raw is None:
        ats_raw = {}
    if isinstance(ats_raw, str):
        text = _clean_text(ats_raw)
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                ats_raw = json.loads(match.group(0))
            except Exception:
                ats_raw = {"JD Match": "0%", "MissingKeywords": [], "Profile Summary": _clean_text(text)}
        else:
            ats_raw = {"JD Match": "0%", "MissingKeywords": [], "Profile Summary": _clean_text(text)}
    jd_match = _clean_text((ats_raw or {}).get("JD Match", ""))
    mk = (ats_raw or {}).get("MissingKeywords", [])
    if isinstance(mk, str):
        mk = [p.strip() for p in re.split(r"[;,\n]", mk) if p.strip()]
    if not isinstance(mk, list):
        mk = [str(mk)]
    mk = [_clean_text(x) for x in mk if str(x).strip()]
    prof = _clean_text((ats_raw or {}).get("Profile Summary", ""))
    return {"JD Match": jd_match, "MissingKeywords": mk, "Profile Summary": prof}

def save_applicants():
    rows = []
    for token, apps in APPLICANTS.items():
        for app_item in apps:
            ats = _sanitize_ats(app_item.get("ats_result", {}))
            jd_match = ats.get("JD Match", "")
            missing_keywords = ", ".join(ats.get("MissingKeywords", [])) if ats.get("MissingKeywords") else "None"
            summary = ats.get("Profile Summary", "")
            parts = []
            if jd_match:
                parts.append(f"Match {jd_match}.")
            parts.append(f"Missing: {missing_keywords}.")
            if summary:
                parts.append(f"Summary: {summary}")
            profile_para = " ".join(parts).strip()
            rows.append({
                "Job Token": app_item.get("job_token", token),
                "ID": app_item.get("id", ""),
                "Applied On": app_item.get("created_at", ""),
                "Name": app_item.get("name", ""),
                "Email": app_item.get("email", ""),
                "Education": app_item.get("education", ""),
                "College": app_item.get("college", ""),
                "Passout": app_item.get("passout", ""),
                "Status": app_item.get("status", ""),
                "JD Match": jd_match,
                "Missing Keywords": missing_keywords,
                "Profile Summary": profile_para
            })
    pd.DataFrame(rows).to_excel(EXCEL_FILE, index=False)
    with open(APPLICANTS_FILE, "w", encoding="utf-8") as f:
        json.dump(APPLICANTS, f, indent=2)
    print(f"✅ Saved {len(rows)} applicants to {EXCEL_FILE}")

def extract_resume_text(uploaded_file: UploadFile):
    reader = pdf.PdfReader(uploaded_file.file)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text
    return text

def run_ats_analysis(resume_text, jd_text):
    prompt = f"""
You are an expert ATS. Evaluate the resume against the job description and provide:

1. JD Match percentage
2. Missing keywords
3. Short profile summary

Resume: {resume_text}

Job Description: {jd_text}

Respond ONLY in valid JSON:
{{"JD Match": "85%", "MissingKeywords": ["keyword1"], "Profile Summary": "short summary here"}}
"""
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)
    try:
        return _sanitize_ats(json.loads(response.text))
    except Exception:
        return _sanitize_ats(response.text)

def send_email_smtp(to_email: str, subject: str, body: str):
    context = {
        "host": SMTP_HOST, "port": SMTP_PORT,
        "user": (SMTP_USER or "")[:2] + "***",
        "use_ssl": SMTP_USE_SSL, "from": (SMTP_FROM or SMTP_USER or "")[:2] + "***",
        "to": to_email,
    }
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS and (SMTP_FROM or SMTP_USER)):
        err = f"Missing SMTP config: {context}"
        print(err)
        return {"ok": False, "error": err}
    sender_email = SMTP_FROM or SMTP_USER
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr((SMTP_FROM_NAME, sender_email))
    msg["To"] = to_email
    try:
        if SMTP_USE_SSL:
            print(f"[SMTP] Connecting via SSL: {context}")
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                server.ehlo(); server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(sender_email, [to_email], msg.as_string())
        else:
            print(f"[SMTP] Connecting with STARTTLS: {context}")
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                server.ehlo(); server.starttls(); server.ehlo()
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(sender_email, [to_email], msg.as_string())
        print(f"[SMTP] Email sent to {to_email}")
        return {"ok": True, "error": ""}
    except Exception as e:
        tb = traceback.format_exc()
        err = f"[SMTP] Send failed: {e.__class__.__name__}: {e}; context={context}\n{tb}"
        print(err)
        return {"ok": False, "error": err}

# --------- HR portal ---------
@app.get("/hr", response_class=HTMLResponse)
def hr_portal():
    with open("static/hr.html", encoding="utf-8") as f:
        return f.read()

@app.post("/hr/create_job")
async def create_job(jd: str = Form(...), designation: str = Form(...)):
    token = str(uuid.uuid4())[:8]
    TOKENS[token] = {"JD": jd, "designation": designation}
    save_tokens()
    return {"token": token, "link": f"/apply/{token}"}

@app.get("/hr/applicants/{token}")
def get_applicants(token: str):
    apps = APPLICANTS.get(token, [])
    out = []
    for a in apps:
        aa = dict(a)
        aa["ats_result"] = _sanitize_ats(a.get("ats_result", {}))
        out.append(aa)
    return out

@app.post("/hr/update_status/{token}/{email}")
def update_status(token: str, email: str, status: str = Form(...)):
    if token not in APPLICANTS:
        raise HTTPException(status_code=404, detail="No applicants found")
    for app_item in APPLICANTS[token]:
        if app_item.get("email") == email:
            app_item["status"] = status
            save_applicants()

            candidate_name = app_item.get("name", "Candidate")
            job_title = TOKENS[token].get("designation", "the role")

            if status.lower() == "selected":
                subject = "Congratulations! Your Application Has Been Accepted"
                body = f"""Dear {candidate_name},
We are delighted to inform you that your application for the {job_title} position has been accepted. 
Our team was impressed by your skills, background, and passion. We believe you will make a strong contribution, and we are excited to move forward with you in the next steps of the hiring process.
Our HR team will contact you shortly with details about onboarding and the next stages.
Thank you once again for your interest in joining our team. We are looking forward to working with you!
Warm regards,
{os.getenv('COMPANY_NAME','Your Company Name')} HR Team"""
            else:
                subject = "Update on Your Application"
                body = f"""Dear {candidate_name},
Thank you for taking the time to apply for the {job_title} position with us.
After careful consideration, we regret to inform you that your application has not been selected for the current role. This was a very competitive process, and while your skills and background are impressive, we had to make some tough choices.
Please don’t be discouraged — we encourage you to apply for future opportunities with us. Your profile remains valuable, and we would be happy to consider you again.
We sincerely wish you the best in your career journey and hope our paths cross again.
Warm regards,
{os.getenv('COMPANY_NAME','Your Company Name')} HR Team"""

            result = send_email_smtp(email, subject, body)
            msg = "Status updated"
            if result.get("ok"):
                msg += " and email sent"
            else:
                msg += " but email could not be sent"
            return {"message": msg, "email_ok": result.get("ok", False), "email_error": result.get("error", "")}

    raise HTTPException(status_code=404, detail="Applicant not found")


# --------- Candidate portal ---------
@app.get("/apply/{token}", response_class=HTMLResponse)
def candidate_portal(token: str):
    if token not in TOKENS:
        raise HTTPException(status_code=404, detail="Invalid token")
    with open("static/candidate.html", encoding="utf-8") as f:
        return f.read()

@app.post("/api/submit_application/{token}")
async def submit_application(
    token: str,
    name: str = Form(...),
    email: str = Form(...),
    education: str = Form(...),
    college: str = Form(...),
    passout: int = Form(...),
    resume: UploadFile = File(...),
):
    if token not in TOKENS:
        raise HTTPException(status_code=404, detail="Invalid token")

    # Basic server-side PDF validation
    filename_lower = (resume.filename or '').lower()
    if not filename_lower.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Read all bytes first
    resume_bytes = await resume.read()

    # Try parsing with PyPDF2 to ensure it's a readable PDF
    try:
        test_reader = pdf.PdfReader(BytesIO(resume_bytes))
        _ = len(test_reader.pages)  # force read
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or corrupted PDF file.")

    # Save using candidate's original filename; only prefix if collision
    orig_name = resume.filename or "resume.pdf"
    orig_name = os.path.basename(orig_name).strip().replace("\\", "/").split("/")[-1]
    if not orig_name.lower().endswith(".pdf"):
        orig_name = orig_name + ".pdf"

    resume_filename = orig_name
    resume_path = os.path.join(RESUME_DIR, resume_filename)
    if os.path.exists(resume_path):
        unique_prefix = str(uuid.uuid4())[:8] + "_"
        resume_filename = unique_prefix + orig_name
        resume_path = os.path.join(RESUME_DIR, resume_filename)

    with open(resume_path, "wb") as f:
        f.write(resume_bytes)

    # Reuse bytes for text extraction
    resume.file = BytesIO(resume_bytes)
    resume_text = extract_resume_text(resume)

    # Run ATS analysis
    ats_result = run_ats_analysis(resume_text, TOKENS[token]["JD"])

    # Build record
    import datetime
    app_data = {
        "id": str(uuid.uuid4())[:8],
        "job_token": token,
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "name": name,
        "email": email,
        "education": education,
        "college": college,
        "passout": passout,
        "ats_result": ats_result,
        "status": "Pending",
        "resume_file": resume_filename,
    }

    if token not in APPLICANTS:
        APPLICANTS[token] = []
    APPLICANTS[token].append(app_data)
    save_applicants()

    return JSONResponse({"status": "success", "message": "Your application is submitted and you will be contacted."})

# --------- Download endpoints ---------
@app.get("/hr/download_resume/{filename}")
def download_resume(filename: str):
    file_path = os.path.join(RESUME_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Resume not found")
    return FileResponse(file_path, filename=filename)

@app.get("/hr/download_excel")
def download_excel():
    if not os.path.exists(EXCEL_FILE):
        raise HTTPException(status_code=404, detail="No data available")
    return FileResponse(EXCEL_FILE, filename="applicants.xlsx")

@app.get("/tokens.json")
def get_tokens_json():
    return TOKENS

@app.get("/hr/smtp_status")
def smtp_status():
    cfg = {
        "SMTP_HOST": os.getenv("SMTP_HOST"),
        "SMTP_PORT": os.getenv("SMTP_PORT"),
        "SMTP_USE_SSL": os.getenv("SMTP_USE_SSL"),
        "SMTP_USER": ((os.getenv("SMTP_USER") or "")[:2] + "***") if os.getenv("SMTP_USER") else None,
        "SMTP_FROM": ((os.getenv("SMTP_FROM") or "")[:2] + "***") if os.getenv("SMTP_FROM") else None,
        "SMTP_FROM_NAME": os.getenv("SMTP_FROM_NAME"),
        "HAS_PASS": bool(os.getenv("SMTP_PASS")),
    }
    return cfg

