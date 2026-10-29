from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text

from .database import Base


class PracticeSession(Base):
    __tablename__ = "practice_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    sentence = Column(String(500), nullable=False)
    pronunciation_score = Column(Float, nullable=False)
    detected_rasa = Column(String(100), nullable=False)
    feedback_type = Column(String(100), nullable=False)
    feedback_timing = Column(String(50), nullable=False)
    feedback = Column(Text, nullable=False)
    retrieved_knowledge = Column(Text, nullable=False)
    next_activity = Column(String(200), nullable=False)
    transcribed_text = Column(Text, nullable=False)
    detected_emotion = Column(String(100), nullable=False)
    emotion_confidence = Column(Float, nullable=False)
    assessment_details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
