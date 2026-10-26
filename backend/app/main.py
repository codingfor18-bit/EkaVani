from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.models.database import Base, engine, get_db
from app.models.practice_session import PracticeSession
from app.models.user import User


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: int
    name: str
    email: str


class AuthResponse(BaseModel):
    message: str
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class PracticeResponse(BaseModel):
    id: int
    learner_id: int
    sentence: str
    pronunciation_score: float
    detected_rasa: str
    feedback_type: str
    feedback_timing: str
    feedback: str
    retrieved_knowledge: str
    next_activity: str
    transcribed_text: str
    detected_emotion: str
    emotion_confidence: float
    created_at: datetime


def settings_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


Base.metadata.create_all(bind=engine)

app = FastAPI(title="EkaVani API", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def auth_payload(user: User, message: str) -> dict:
    return {
        "message": message,
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": {"id": user.id, "name": user.name, "email": user.email},
    }


@app.post("/api/v1/auth/register", response_model=AuthResponse, status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be blank")
    email = str(data.email).strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(name=name, email=email, password_hash=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not create account")
    return auth_payload(user, "Registration successful")


@app.post("/api/v1/auth/login", response_model=AuthResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    email = str(data.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return auth_payload(user, "Login successful")


KNOWLEDGE_BASE = {
    "bonjour": "The French 'on' sound is nasal. Let the sound resonate through the nose.",
    "café": "Keep the final 'é' as a clear closed vowel, without an English diphthong.",
    "français": "The 'an' sound is a nasal vowel; avoid pronouncing a strong final n.",
    "rouge": "French 'r' is produced toward the back of the throat rather than as an English r.",
}


def retrieve_knowledge(text: str) -> str:
    normalized = text.casefold()
    for word, guidance in KNOWLEDGE_BASE.items():
        if word in normalized:
            return guidance
    return "Focus on French vowel quality, consonant accuracy, rhythm, and intonation."


def analyze_pronunciation(audio_path: str, transcript: str, expected: str) -> float:
    """Prototype match score; this is not a phoneme-level pronunciation assessment."""
    from rapidfuzz.fuzz import ratio

    if not transcript.strip():
        return 0.0
    return round(float(ratio(transcript.casefold().strip(), expected.casefold().strip())), 1)


def transcribe_and_detect(audio_path: str) -> tuple[str, str, str, float]:
    """Load heavyweight speech models on first use so auth and health start quickly."""
    try:
        import whisper
        from transformers import pipeline
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="Speech analysis dependencies are missing. Install backend requirements and restart.",
        ) from exc

    global whisper_model, emotion_classifier
    try:
        if whisper_model is None:
            whisper_model = whisper.load_model(os.getenv("WHISPER_MODEL", "base"))
        if emotion_classifier is None:
            emotion_classifier = pipeline(
                "audio-classification", model="superb/wav2vec2-base-superb-er"
            )
        result = whisper_model.transcribe(
            audio_path,
            language="fr",
            task="transcribe",
            temperature=0,
            condition_on_previous_text=False,
        )
        transcript = result.get("text", "").strip()
        emotions = emotion_classifier(audio_path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not analyze this audio: {exc}") from exc

    emotion_result = emotions[0] if emotions else {"label": "neu", "score": 0.0}
    label = str(emotion_result["label"]).lower()
    confidence = round(float(emotion_result["score"]) * 100, 1)
    emotion_to_rasa = {
        "neu": ("Shanta (Calm)", "neutral"),
        "hap": ("Hasya (Joy)", "happy"),
        "ang": ("Raudra (Anger)", "angry"),
        "sad": ("Karuna (Compassion)", "sad"),
        "fear": ("Bhayanaka (Fear)", "fear"),
        "dis": ("Bibhatsa (Disgust)", "disgust"),
    }
    rasa, emotion = emotion_to_rasa.get(label, ("Shanta (Calm)", label))
    return transcript, rasa, emotion, confidence


whisper_model = None
emotion_classifier = None


def feedback_for(score: float) -> tuple[str, str, str, str]:
    if score < 60:
        return (
            "Encouraging", "Delayed",
            "Take your time. Repeat the phrase slowly and build confidence.",
            "Repeat the pronunciation exercise",
        )
    if score < 80:
        return (
            "Corrective + Encouraging", "Immediate",
            "Good focus. Refine the target sound while keeping your natural rhythm.",
            "Practise similar French words",
        )
    return (
        "Exploratory", "Immediate",
        "Great work. Try another sentence using the same pronunciation pattern.",
        "Attempt a new conversational sentence",
    )


@app.post("/api/v1/practice/analyze", response_model=PracticeResponse)
async def analyze_practice(
    audio: UploadFile = File(...),
    sentence: str = Form(..., min_length=1, max_length=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filename = (audio.filename or "").lower()
    allowed_types = {"audio/webm", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/ogg"}
    if audio.content_type not in allowed_types and Path(filename).suffix not in {
        ".webm", ".wav", ".mp3", ".m4a", ".ogg", ".mpeg"
    }:
        raise HTTPException(status_code=415, detail="Unsupported audio format")
    limit = 15 * 1024 * 1024
    content = await audio.read(limit + 1)
    await audio.close()
    if not content:
        raise HTTPException(status_code=422, detail="The recording is empty")
    if len(content) > limit:
        raise HTTPException(status_code=413, detail="Audio must be 15 MB or smaller")

    suffix = Path(filename).suffix or ".webm"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="ekavani-", suffix=suffix, delete=False) as temp:
            temp.write(content)
            temp_path = temp.name
        transcript, rasa, emotion, confidence = transcribe_and_detect(temp_path)
        score = analyze_pronunciation(temp_path, transcript, sentence)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    knowledge = retrieve_knowledge(transcript)
    feedback_type, timing, feedback, next_activity = feedback_for(score)
    record = PracticeSession(
        user_id=current_user.id,
        sentence=sentence.strip(),
        pronunciation_score=score,
        detected_rasa=rasa,
        feedback_type=feedback_type,
        feedback_timing=timing,
        feedback=feedback,
        retrieved_knowledge=knowledge,
        next_activity=next_activity,
        transcribed_text=transcript,
        detected_emotion=emotion,
        emotion_confidence=confidence,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return session_response(record)


def session_response(record: PracticeSession) -> dict:
    response = {
        column.name: getattr(record, column.name)
        for column in PracticeSession.__table__.columns
    }
    response["learner_id"] = response.pop("user_id")
    return response


@app.get("/api/v1/practice/history", response_model=list[PracticeResponse])
def practice_history(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if limit < 1 or limit > 100 or offset < 0:
        raise HTTPException(status_code=422, detail="Use limit 1–100 and a non-negative offset")
    records = (
        db.query(PracticeSession)
        .filter(PracticeSession.user_id == current_user.id)
        .order_by(desc(PracticeSession.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [session_response(record) for record in records]


@app.get("/api/v1/practice/progress")
def practice_progress(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    records = (
        db.query(PracticeSession)
        .filter(PracticeSession.user_id == current_user.id)
        .order_by(PracticeSession.created_at)
        .all()
    )
    scores = [record.pronunciation_score for record in records]
    return {
        "session_count": len(records),
        "average_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "latest_score": scores[-1] if scores else 0,
        "scores": [
            {"score": record.pronunciation_score, "created_at": record.created_at}
            for record in records[-10:]
        ],
    }


@app.get("/api/v1/auth/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "name": current_user.name, "email": current_user.email}


@app.get("/")
def root():
    return {"system": "EkaVani", "status": "running"}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok", "service": "ekavani-api"}
