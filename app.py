from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from PIL import Image
import io, os, uuid, datetime, traceback, sqlite3
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from typing import Optional, List

from predict import predict_cancer
from report_generator import generate_pdf_report
from batch_report_generator import generate_batch_pdf_report

SECRET_KEY = "onchoscan-k9Xm2Pv7Lq4Rn8Wj1Yb5Tz3Hs6Fu"
ALGORITHM  = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

app = FastAPI(title="OnchoScan – Multi Cancer Detection API")

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    traceback.print_exc()
    return PlainTextResponse(str(exc), status_code=500)

os.makedirs("outputs", exist_ok=True)
os.makedirs("reports", exist_ok=True)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")
app.mount("/reports",  StaticFiles(directory="reports"),  name="reports")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ashwin007-ai.github.io",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── SQLite ─────────────────────────────────────────────────────────────────────
DB_PATH = "onchoscan.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username         TEXT PRIMARY KEY,
            email            TEXT NOT NULL,
            full_name        TEXT,
            hashed_password  TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id               TEXT PRIMARY KEY,
            username         TEXT NOT NULL,
            timestamp        TEXT NOT NULL,
            cancer_type      TEXT,
            prediction       TEXT,
            confidence       REAL,
            risk_level       TEXT,
            report           TEXT,
            patient_name     TEXT,
            patient_age      TEXT,
            patient_sex      TEXT,
            patient_symptoms TEXT,
            patient_note     TEXT,
            FOREIGN KEY (username) REFERENCES users(username)
        )
    """)
    conn.commit()

    # Safe migrations — add any missing columns without breaking existing data
    migrations = [
        ("predictions", "analysis_type", "TEXT DEFAULT 'single'"),
        ("users", "phone",     "TEXT DEFAULT ''"),
        ("users", "dob",       "TEXT DEFAULT ''"),
        ("users", "gender",    "TEXT DEFAULT ''"),
        ("users", "role",      "TEXT DEFAULT ''"),
        ("users", "org",       "TEXT DEFAULT ''"),
        ("users", "city",      "TEXT DEFAULT ''"),
        ("users", "country",   "TEXT DEFAULT ''"),
        ("users", "bio",       "TEXT DEFAULT ''"),
        ("users", "specs",     "TEXT DEFAULT ''"),
        ("users", "avatar",    "TEXT DEFAULT ''"),
        ("users", "join_date", "TEXT DEFAULT ''"),
        ("users", "last_login","TEXT DEFAULT ''"),
        ("users", "prefs",     "TEXT DEFAULT '{}'"),
    ]
    for table, col, col_def in migrations:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
            conn.commit()
        except Exception:
            pass

    conn.close()
    print("SQLite database initialized:", DB_PATH)

init_db()

# ── Auth helpers ───────────────────────────────────────────────────────────────
pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

class UserCreate(BaseModel):
    username:  str
    email:     str
    password:  str
    full_name: Optional[str] = ""

class Token(BaseModel):
    access_token: str
    token_type:   str
    username:     str
    full_name:    str

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = ""
    email:     Optional[str] = ""
    phone:     Optional[str] = ""
    dob:       Optional[str] = ""
    gender:    Optional[str] = ""
    role:      Optional[str] = ""
    org:       Optional[str] = ""
    city:      Optional[str] = ""
    country:   Optional[str] = ""
    bio:       Optional[str] = ""
    specs:     Optional[str] = ""
    avatar:    Optional[str] = ""
    prefs:     Optional[str] = ""

class ChangePassword(BaseModel):
    current_password: str
    new_password:     str

def verify_password(plain, hashed): return pwd_context.verify(plain, hashed)
def hash_password(p):               return pwd_context.hash(p)

def create_access_token(data: dict, expires_delta=None):
    to_encode = data.copy()
    expire    = datetime.datetime.utcnow() + (expires_delta or datetime.timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    exc = HTTPException(status_code=401, detail="Could not validate credentials",
                        headers={"WWW-Authenticate": "Bearer"})
    try:
        payload  = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username: raise exc
    except JWTError:
        raise exc
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if not user: raise exc
    return dict(user)

# ── Routes ─────────────────────────────────────────────────────────────────────
@app.get("/")
def home():
    landing = os.path.join(os.path.dirname(os.path.abspath(__file__)), "landing.html")
    if os.path.exists(landing):
        return FileResponse(landing, media_type="text/html")
    return {"message": "OnchoScan API running"}

@app.post("/register", response_model=Token)
def register(user: UserCreate):
    conn = get_db()
    existing = conn.execute("SELECT username FROM users WHERE username=?", (user.username,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")
    join_date  = datetime.datetime.now().strftime("%B %Y")
    last_login = datetime.datetime.now().isoformat()
    conn.execute(
        "INSERT INTO users (username, email, full_name, hashed_password, join_date, last_login) VALUES (?,?,?,?,?,?)",
        (user.username, user.email, user.full_name or "", hash_password(user.password), join_date, last_login)
    )
    conn.commit()
    conn.close()
    token = create_access_token({"sub": user.username},
                                datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return Token(access_token=token, token_type="bearer",
                 username=user.username, full_name=user.full_name or user.username)

@app.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (form_data.username,)).fetchone()
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        conn.close()
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    conn.execute("UPDATE users SET last_login=? WHERE username=?",
                 (datetime.datetime.now().isoformat(), form_data.username))
    conn.commit()
    conn.close()
    token = create_access_token({"sub": form_data.username},
                                datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return Token(access_token=token, token_type="bearer",
                 username=user["username"], full_name=user["full_name"] or user["username"])

@app.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM predictions WHERE username=?",
        (current_user["username"],)
    ).fetchone()[0]
    conn.close()
    return {"username": current_user["username"], "email": current_user["email"],
            "full_name": current_user["full_name"], "total_predictions": count}

# ── GET Profile ────────────────────────────────────────────────────────────────
@app.get("/profile")
def get_profile(current_user: dict = Depends(get_current_user)):
    safe = {k: v for k, v in current_user.items() if k != "hashed_password"}
    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM predictions WHERE username=?",
        (current_user["username"],)
    ).fetchone()[0]
    conn.close()
    safe["total_scans"] = count
    return safe

# ── PUT Profile ────────────────────────────────────────────────────────────────
@app.put("/profile")
def update_profile(data: ProfileUpdate, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    conn.execute("""
        UPDATE users SET
            full_name = CASE WHEN ? != '' THEN ? ELSE full_name END,
            email     = CASE WHEN ? != '' THEN ? ELSE email END,
            phone     = ?,
            dob       = ?,
            gender    = ?,
            role      = ?,
            org       = ?,
            city      = ?,
            country   = ?,
            bio       = ?,
            specs     = ?,
            avatar    = CASE WHEN ? != '' THEN ? ELSE avatar END,
            prefs     = CASE WHEN ? != '' THEN ? ELSE prefs END
        WHERE username = ?
    """, (
        data.full_name, data.full_name,
        data.email,     data.email,
        data.phone, data.dob, data.gender, data.role,
        data.org, data.city, data.country, data.bio, data.specs,
        data.avatar, data.avatar,
        data.prefs,  data.prefs,
        current_user["username"]
    ))
    conn.commit()
    conn.close()
    return {"ok": True, "message": "Profile updated"}

# ── Change Password ────────────────────────────────────────────────────────────
@app.post("/change-password")
def change_password(data: ChangePassword, current_user: dict = Depends(get_current_user)):
    if not verify_password(data.current_password, current_user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    conn = get_db()
    conn.execute("UPDATE users SET hashed_password=? WHERE username=?",
                 (hash_password(data.new_password), current_user["username"]))
    conn.commit()
    conn.close()
    return {"ok": True, "message": "Password changed successfully"}

# ── Delete Account ─────────────────────────────────────────────────────────────
@app.delete("/account")
def delete_account(current_user: dict = Depends(get_current_user)):
    username = current_user["username"]
    conn = get_db()
    conn.execute("DELETE FROM predictions WHERE username=?", (username,))
    conn.execute("DELETE FROM users WHERE username=?", (username,))
    conn.commit()
    conn.close()
    return {"ok": True, "message": "Account permanently deleted"}

@app.post("/predict")
async def predict(
    file:             UploadFile = File(...),
    cancer_type:      str        = Form(...),
    patient_name:     str        = Form(""),
    patient_age:      str        = Form(""),
    patient_sex:      str        = Form(""),
    patient_symptoms: str        = Form(""),
    patient_note:     str        = Form(""),
    current_user:     dict       = Depends(get_current_user)):

    contents = await file.read()
    image    = Image.open(io.BytesIO(contents)).convert("RGB")
    result   = predict_cancer(image, cancer_type)

    patient_info = {
        "patient_name":     patient_name,
        "patient_age":      patient_age,
        "patient_sex":      patient_sex,
        "patient_symptoms": patient_symptoms,
        "patient_note":     patient_note,
    }
    result.update(patient_info)
    report_path = generate_pdf_report(result, result["heatmap"], result.get("original"), patient_info)
    result["report"] = report_path

    conn = get_db()
    conn.execute(
        """INSERT INTO predictions
           (id, username, timestamp, cancer_type, prediction, confidence,
            risk_level, report, patient_name, patient_age, patient_sex,
            patient_symptoms, patient_note, analysis_type)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (str(uuid.uuid4()), current_user["username"],
         datetime.datetime.now().isoformat(),
         cancer_type, result["prediction"], result["confidence"],
         result["risk_level"], report_path,
         patient_name, patient_age, patient_sex, patient_symptoms, patient_note, "single")
    )
    conn.commit()
    conn.close()
    return result

@app.post("/predict/batch")
async def predict_batch(
    files:        List[UploadFile] = File(...),
    cancer_type:  str              = Form(...),
    current_user: dict             = Depends(get_current_user)):

    results = []
    conn = get_db()
    for file in files:
        try:
            contents = await file.read()
            image    = Image.open(io.BytesIO(contents)).convert("RGB")
            result   = predict_cancer(image, cancer_type)
            report_path = generate_pdf_report(result, result["heatmap"], result.get("original"), {})
            result["report"]    = report_path
            result["filename"]  = file.filename
            result["error"]     = None
            conn.execute(
                """INSERT INTO predictions
                   (id, username, timestamp, cancer_type, prediction, confidence,
                    risk_level, report, patient_name, patient_age, patient_sex,
                    patient_symptoms, patient_note, analysis_type)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), current_user["username"],
                 datetime.datetime.now().isoformat(),
                 cancer_type, result["prediction"], result["confidence"],
                 result["risk_level"], report_path,
                 "", "", "", "", "", "batch")
            )
            conn.commit()
        except Exception as e:
            result = {"filename": file.filename, "error": str(e)}
        results.append(result)
    conn.close()
    return {
        "results":     results,
        "total":       len(results),
        "high_risk":   sum(1 for r in results if r.get("risk_level") == "High Risk"),
        "medium_risk": sum(1 for r in results if r.get("risk_level") == "Medium Risk"),
        "low_risk":    sum(1 for r in results if r.get("risk_level") == "Low Risk"),
    }

@app.post("/predict/batch/combined-pdf")
async def batch_combined_pdf(
    files:        List[UploadFile] = File(...),
    cancer_type:  str              = Form(...),
    current_user: dict             = Depends(get_current_user)):
    all_results = []
    for file in files:
        try:
            contents = await file.read()
            image    = Image.open(io.BytesIO(contents)).convert("RGB")
            result   = predict_cancer(image, cancer_type)
            result["filename"] = file.filename
            result["error"]    = None
            all_results.append(result)
        except Exception as e:
            all_results.append({"filename": file.filename, "error": str(e)})
    combined_path = generate_batch_pdf_report(all_results, cancer_type)
    return FileResponse(combined_path, media_type="application/pdf",
                        filename=f"OnchoScan_Batch_Report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

@app.get("/history")
def history(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM predictions WHERE username=? ORDER BY timestamp DESC",
        (current_user["username"],)
    ).fetchall()
    conn.close()
    return {"history": [dict(r) for r in rows]}