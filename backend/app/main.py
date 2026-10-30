from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import desc, text
from sqlalchemy.orm import Session
from fastapi.staticfiles import StaticFiles

from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.learning import (
    PRACTICE_LEVELS,
    PRACTICE_SENTENCES,
    RASA_PROFILES,
    assess_speech,
    generate_grounded_feedback,
    infer_rasa,
    retrieve_guidance,
    summarize_progress,
    validate_rasa,
)
from app.models.database import Base, engine, ensure_assessment_details_column, get_db
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
    assessment: dict = Field(default_factory=dict)
    created_at: datetime


FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
ASR_BENCHMARK_FILE = Path(__file__).resolve().parent / "data" / "asr_benchmark.json"


def settings_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


Base.metadata.create_all(bind=engine)
ensure_assessment_details_column()

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


def extract_pitch_features(audio_path: str) -> dict:
    """Describe pitch movement when librosa is installed; do not grade it."""
    try:
        import librosa
        import numpy as np

        samples, sample_rate = librosa.load(audio_path, sr=16000, mono=True)
        if samples.size < sample_rate // 4:
            return {"pitch_analysis": "unavailable: recording is too short"}
        pitch = librosa.yin(samples, fmin=70, fmax=400, sr=sample_rate)
        pitch = pitch[np.isfinite(pitch)]
        if pitch.size < 4:
            return {"pitch_analysis": "unavailable: no stable voiced pitch found"}
        quarter = max(1, pitch.size // 4)
        first = float(np.median(pitch[:quarter]))
        last = float(np.median(pitch[-quarter:]))
        delta = last - first
        contour = "rising" if delta >= 15 else "falling" if delta <= -15 else "mostly level"
        return {
            "pitch_mean_hz": round(float(np.median(pitch)), 1),
            "pitch_range_hz": round(float(np.percentile(pitch, 90) - np.percentile(pitch, 10)), 1),
            "final_pitch_change_hz": round(delta, 1),
            "final_pitch_contour": contour,
            "prosody_note": "Acoustic description only; no validated intonation target is available.",
        }
    except ImportError:
        return {"pitch_analysis": "unavailable: install backend/requirements-speech.txt"}
    except Exception as exc:
        return {"pitch_analysis": f"unavailable: {type(exc).__name__}"}


def transcribe_and_detect(audio_path: str) -> dict:
    """Transcribe French and estimate one of the SER checkpoint's four labels."""
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
            word_timestamps=True,
        )
        transcript = result.get("text", "").strip()
        emotions = emotion_classifier(audio_path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not analyze this audio: {exc}") from exc

    emotion_result = emotions[0] if emotions else {"label": "neu", "score": 0.0}
    return {
        "transcript": transcript,
        "emotion_label": str(emotion_result["label"]).lower(),
        "emotion_confidence": round(float(emotion_result["score"]) * 100, 1),
        "segments": result.get("segments", []),
    }


whisper_model = None
emotion_classifier = None


@app.post("/api/v1/practice/analyze", response_model=PracticeResponse)
async def analyze_practice(
    audio: UploadFile = File(...),
    sentence: str = Form(..., min_length=1, max_length=500),
    learner_rasa: str | None = Form(default=None),
    feedback_style: str = Form(default="adaptive"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sentence = sentence.strip()
    if not sentence:
        raise HTTPException(status_code=422, detail="Choose a non-empty practice sentence")
    chosen_rasa = validate_rasa(learner_rasa)
    if learner_rasa and not chosen_rasa:
        raise HTTPException(status_code=422, detail="Unknown Navarasa selection")
    if feedback_style not in {"adaptive", "supportive", "direct"}:
        raise HTTPException(status_code=422, detail="Unknown feedback style")

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
        speech = transcribe_and_detect(temp_path)
        transcript = speech["transcript"]
        assessment = assess_speech(sentence, transcript, speech.get("segments", []))
        assessment.update(extract_pitch_features(temp_path))
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    model_rasa, rasa_source = infer_rasa(
        speech["emotion_label"], speech["emotion_confidence"]
    )
    rasa = chosen_rasa or model_rasa
    if chosen_rasa:
        rasa_source = "learner-selected"
    assessment["rasa"] = rasa
    assessment["rasa_source"] = rasa_source
    assessment["ser_supported_labels"] = ["ang", "hap", "neu", "sad"]
    assessment["assessment_limitations"] = [
        "Word-match score measures transcript content, not phoneme accuracy.",
        "Intelligibility is represented only by an ASR confidence proxy.",
        "Pitch is described acoustically and is not judged against a validated prosody target.",
        "The speech emotion model has four labels; the nine-rasa selection is an adaptation framework, not nine-class SER.",
    ]
    guidance = retrieve_guidance(sentence, transcript, assessment)
    generated = generate_grounded_feedback(
        sentence, transcript, assessment, guidance, rasa, rasa_source, feedback_style
    )
    knowledge = "\n\n".join(
        f"[{item['id']}] {item['title']}: {item['content']} Practice cue: {item['drill']}"
        for item in guidance
    )
    assessment["feedback_sources"] = [item["id"] for item in guidance]
    record = PracticeSession(
        user_id=current_user.id,
        sentence=sentence,
        pronunciation_score=assessment["word_match_score"],
        detected_rasa=f"{rasa} ({RASA_PROFILES[rasa]['meaning']})",
        feedback_type=generated["feedback_type"],
        feedback_timing=generated["feedback_timing"],
        feedback=generated["feedback"],
        retrieved_knowledge=knowledge,
        next_activity=generated["next_activity"],
        transcribed_text=transcript,
        detected_emotion=speech["emotion_label"],
        emotion_confidence=speech["emotion_confidence"],
        assessment_details=assessment,
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
    response["assessment"] = response.pop("assessment_details", None) or {}
    return response


@app.get("/api/v1/practice/sentences")
def practice_sentences(level: str | None = None):
    if level is None:
        return PRACTICE_SENTENCES
    normalized_level = level.upper()
    if normalized_level not in PRACTICE_LEVELS:
        raise HTTPException(status_code=422, detail="Level must be A1, A2, B1, B2, C1, or C2")
    return [sentence for sentence in PRACTICE_SENTENCES if sentence["level"] == normalized_level]


@app.get("/api/v1/evaluation/asr")
def asr_evaluation():
    if not ASR_BENCHMARK_FILE.is_file():
        raise HTTPException(status_code=503, detail="No French corpus evaluation report is available")
    return json.loads(ASR_BENCHMARK_FILE.read_text(encoding="utf-8"))


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
    return summarize_progress([
        {
            "pronunciation_score": record.pronunciation_score,
            "created_at": record.created_at.isoformat(),
            "assessment_details": record.assessment_details,
        }
        for record in records
    ])


@app.get("/api/v1/auth/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "name": current_user.name, "email": current_user.email}


@app.get("/")
def root():
    index_file = FRONTEND_DIST / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return {"system": "EkaVani", "status": "running"}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok", "service": "ekavani-api"}


if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
