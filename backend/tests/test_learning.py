"""Evaluation tests for EkaVani's transparent speech-feedback pipeline."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.learning import (
    PRACTICE_LEVELS,
    PRACTICE_SENTENCES,
    RASA_PROFILES,
    assess_speech,
    generate_grounded_feedback,
    infer_rasa,
    retrieve_guidance,
    validate_rasa,
    word_errors,
)


class SpeechAssessmentTests(unittest.TestCase):
    def test_practice_prompts_cover_custom_difficulty_groups(self):
        self.assertEqual({item["level"] for item in PRACTICE_SENTENCES}, set(PRACTICE_LEVELS))
        self.assertEqual(len(PRACTICE_SENTENCES), 60)
        for level in PRACTICE_LEVELS:
            self.assertEqual(sum(item["level"] == level for item in PRACTICE_SENTENCES), 10)
        source_mapping = {"A1": "C2", "A2": "C1", "B1": "B2", "B2": "B1", "C1": "A2", "C2": "A1"}
        for level, source_level in source_mapping.items():
            rows = [item for item in PRACTICE_SENTENCES if item["level"] == level]
            self.assertTrue(all(item["source_level"] == source_level for item in rows))

    def test_exact_match_is_case_punctuation_and_accent_insensitive(self):
        result = word_errors("Je voudrais un café, s'il vous plaît.", "JE VOUDRAIS UN cafe s'il vous plait")
        self.assertTrue(result["exact_match"])
        self.assertEqual(result["word_error_rate"], 0)
        self.assertEqual(result["word_match_score"], 100)

    def test_alignment_reports_substitutions_omissions_and_insertions(self):
        result = word_errors("Je veux un café aujourd'hui", "Je prends café aujourd'hui demain")
        self.assertTrue(result["substitutions"])
        self.assertTrue(result["omissions"])
        self.assertTrue(result["insertions"])
        self.assertEqual(result["word_error_rate"], 0.6)
        self.assertEqual(result["word_match_score"], 40)
        self.assertEqual(result["word_precision"], 60)
        self.assertEqual(result["word_recall"], 60)
        self.assertEqual(result["word_f1"], 60)
        self.assertGreater(result["character_error_rate"], 0)

    def test_timing_metrics_are_descriptors_not_a_fluency_grade(self):
        result = assess_speech(
            "Bonjour comment allez-vous",
            "Bonjour comment allez-vous",
            [
                {"start": 0, "end": 1, "avg_logprob": -0.2, "no_speech_prob": 0.01},
                {"start": 2, "end": 3, "avg_logprob": -0.4, "no_speech_prob": 0.02},
            ],
        )
        self.assertEqual(result["pause_count_over_0_7s"], 1)
        self.assertEqual(result["speaking_rate_words_per_minute"], 80)
        self.assertIn("no validated fluency threshold", result["fluency_interpretation"])
        self.assertIn("ASR confidence proxy", result["intelligibility_note"])


class RetrievalAndAdaptationTests(unittest.TestCase):
    def test_retrieval_uses_target_and_aligned_error_then_feedback_uses_context(self):
        assessment = word_errors("Je voudrais un café", "Je voudrais un cafe")
        guidance = retrieve_guidance("Je voudrais un café", "Je voudrais un cafe", assessment)
        self.assertEqual(guidance[0]["id"], "closed-e")
        feedback = generate_grounded_feedback(
            "Je voudrais un café", "Je voudrais un cafe", assessment, guidance,
            "Karuna", "learner-selected",
        )
        self.assertIn(guidance[0]["content"], feedback["feedback"])
        self.assertEqual(feedback["knowledge_source"], "closed-e")
        self.assertIn("Gentle", feedback["feedback"])

    def test_supported_ser_labels_map_to_rasa_and_low_confidence_defaults(self):
        self.assertEqual(infer_rasa("hap", 90), ("Hasya", "speech-model"))
        self.assertEqual(infer_rasa("ang", 75)[0], "Raudra")
        self.assertEqual(infer_rasa("sad", 75)[0], "Karuna")
        self.assertEqual(infer_rasa("neu", 75)[0], "Shanta")
        self.assertEqual(infer_rasa("hap", 39), ("Shanta", "low-confidence-default"))
        self.assertEqual(len(RASA_PROFILES), 9)
        self.assertEqual(validate_rasa("adbhuta"), "Adbhuta")
        self.assertIsNone(validate_rasa("unknown"))

    def test_style_changes_feedback_delivery_tone(self):
        assessment = word_errors("bonjour", "bonjour")
        guidance = retrieve_guidance("bonjour", "bonjour", assessment)
        adaptive = generate_grounded_feedback("bonjour", "bonjour", assessment, guidance, "Hasya", "speech-model")
        direct = generate_grounded_feedback("bonjour", "bonjour", assessment, guidance, "Hasya", "speech-model", "direct")
        self.assertIn("Playful and motivating", adaptive["feedback"])
        self.assertIn("Clear and direct", direct["feedback"])


class PracticeApiIntegrationTests(unittest.TestCase):
    """Exercise auth, uploaded audio, feedback persistence, history and progress."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.db_file.close()
        self.engine = create_engine(
            f"sqlite:///{self.db_file.name}",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        from app.main import app
        from app.models.database import Base, get_db

        Base.metadata.create_all(bind=self.engine)

        def override_get_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.engine.dispose()
        Path(self.db_file.name).unlink(missing_ok=True)

    def test_recording_to_grounded_feedback_and_saved_progress(self):
        from app import main

        registration = self.client.post(
            "/api/v1/auth/register",
                json={"name": "Evaluation Learner", "email": "eval@example.com", "password": "test-password-123"},
        )
        self.assertEqual(registration.status_code, 201, registration.text)
        token = registration.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        target = "Je voudrais un café, s'il vous plaît."
        fake_asr = {
            "transcript": "Je voudrais un cafe s'il vous plait",
            "emotion_label": "hap",
            "emotion_confidence": 91.0,
            "segments": [{"start": 0, "end": 2, "avg_logprob": -0.2, "no_speech_prob": 0.01}],
        }
        with patch.object(main, "transcribe_and_detect", return_value=fake_asr) as transcribe, patch.object(
            main, "extract_pitch_features", return_value={"pitch_analysis": "test fixture"}
        ):
            response = self.client.post(
                "/api/v1/practice/analyze",
                headers=headers,
                data={"sentence": target, "feedback_style": "adaptive"},
                files={"audio": ("practice.wav", b"audio fixture", "audio/wav")},
            )
        self.assertEqual(response.status_code, 200, response.text)
        transcribe.assert_called_once()
        saved = response.json()
        self.assertEqual(saved["pronunciation_score"], 100)
        self.assertIn("closed-e", saved["assessment"]["feedback_sources"])
        self.assertIn("closed-e", saved["retrieved_knowledge"])
        self.assertIn("clear closed vowel", saved["feedback"])
        self.assertEqual(saved["detected_emotion"], "hap")
        self.assertIn("Hasya", saved["detected_rasa"])

        history = self.client.get("/api/v1/practice/history", headers=headers)
        progress = self.client.get("/api/v1/practice/progress", headers=headers)
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.json()), 1)
        self.assertEqual(progress.status_code, 200)
        self.assertEqual(progress.json()["session_count"], 1)
        self.assertEqual(progress.json()["latest_score"], 100)
        self.assertEqual(saved["assessment"]["word_precision"], 100)
        self.assertEqual(saved["assessment"]["word_recall"], 100)
        self.assertEqual(saved["assessment"]["word_f1"], 100)
        self.assertGreaterEqual(saved["assessment"]["character_error_rate"], 0)
        all_sentences = self.client.get("/api/v1/practice/sentences")
        self.assertEqual(all_sentences.status_code, 200)
        self.assertEqual(len(all_sentences.json()), 60)
        self.assertEqual(len(self.client.get("/api/v1/practice/sentences?level=c1").json()), 10)
        self.assertEqual(len(self.client.get("/api/v1/practice/sentences?level=C2").json()), 10)
        self.assertEqual(self.client.get("/api/v1/practice/sentences?level=C3").status_code, 422)
        benchmark = self.client.get("/api/v1/evaluation/asr")
        self.assertEqual(benchmark.status_code, 200)
        self.assertEqual(benchmark.json()["sample_size"], 25)
        self.assertGreater(benchmark.json()["word_f1"], 0)
        self.assertFalse(os.path.exists(transcribe.call_args.args[0]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
