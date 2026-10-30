"""Speech-to-feedback helpers that are deterministic and inspectable."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher
from typing import Any


PRACTICE_DATA_FILE = Path(__file__).resolve().parent / "data" / "french_practice_sentences.json"
with PRACTICE_DATA_FILE.open(encoding="utf-8") as practice_file:
    PRACTICE_SENTENCES: list[dict[str, str]] = json.load(practice_file)

PRACTICE_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")

RASA_PROFILES: dict[str, dict[str, str]] = {
    "Sringara": {
        "meaning": "appreciation",
        "tone": "warm and appreciative",
        "adaptation": "connect the correction to a phrase the learner already said well",
        "next": "Say the same phrase once more, then add one personal detail.",
    },
    "Hasya": {
        "meaning": "joy",
        "tone": "playful and motivating",
        "adaptation": "turn the target sound into a short, low-pressure sound challenge",
        "next": "Repeat the target sound in three short, playful phrases.",
    },
    "Karuna": {
        "meaning": "compassion",
        "tone": "gentle and supportive",
        "adaptation": "offer one correction at a time and allow a slower repetition",
        "next": "Repeat only the difficult word slowly, then return to the full phrase.",
    },
    "Raudra": {
        "meaning": "anger",
        "tone": "calm and non-judgmental",
        "adaptation": "remove urgency and focus on one neutral observation",
        "next": "Take a short pause, then try one relaxed repetition.",
    },
    "Vira": {
        "meaning": "courage",
        "tone": "confident and challenging",
        "adaptation": "recognize effort and offer a small next-step challenge",
        "next": "Use the corrected sound in a new sentence of your own.",
    },
    "Bhayanaka": {
        "meaning": "fear",
        "tone": "reassuring and predictable",
        "adaptation": "reduce the task to a manageable word before the full sentence",
        "next": "Practise one word first; repeat the full sentence only when ready.",
    },
    "Bibhatsa": {
        "meaning": "disgust",
        "tone": "neutral and constructive",
        "adaptation": "use factual sound guidance without evaluative language",
        "next": "Compare the target sound with the example, then repeat once.",
    },
    "Adbhuta": {
        "meaning": "wonder",
        "tone": "curious and exploratory",
        "adaptation": "invite the learner to notice how the sound changes in context",
        "next": "Try the sound in a new phrase and notice what changes.",
    },
    "Shanta": {
        "meaning": "calm",
        "tone": "steady and focused",
        "adaptation": "keep the pace even and give one concise cue",
        "next": "Repeat the phrase at a comfortable, even pace.",
    },
}


# The SUPERB emotion-recognition checkpoint used in this app has four labels.
# These mappings deliberately do not claim that it recognizes all nine rasas.
SER_RASA_MAP = {
    "hap": "Hasya",
    "ang": "Raudra",
    "sad": "Karuna",
    "neu": "Shanta",
    "happy": "Hasya",
    "angry": "Raudra",
    "sadness": "Karuna",
    "neutral": "Shanta",
}


KNOWLEDGE_BASE: list[dict[str, Any]] = [
    {
        "id": "nasal-on",
        "title": "Nasal vowel /ɔ̃/ (on)",
        "triggers": {"bonjour", "bon", "on", "maison", "garcon", "non"},
        "content": "For French on, keep the vowel nasal and do not pronounce a separate final n. Example: bonjour.",
        "drill": "Alternate bon and beau; keep the final n silent in bon.",
    },
    {
        "id": "nasal-an",
        "title": "Nasal vowel /ɑ̃/ (an/en)",
        "triggers": {"francais", "enfant", "dans", "temps", "chambre", "parle"},
        "content": "For an/en, sustain the nasal vowel without adding a strong final n. Example: francais.",
        "drill": "Say dans, then dans la chambre, keeping the vowel connected.",
    },
    {
        "id": "nasal-in",
        "title": "Nasal vowel /ɛ̃/ (in/ain)",
        "triggers": {"vin", "pain", "matin", "important", "bien", "demain"},
        "content": "For in/ain, use a nasal vowel; do not turn the ending into an English-style n. Example: demain.",
        "drill": "Contrast vin and vie, then repeat demain at a steady pace.",
    },
    {
        "id": "french-r",
        "title": "French uvular r",
        "triggers": {"rouge", "rue", "tres", "francais", "voudrais", "frere", "paris", "parler"},
        "content": "French r is formed toward the back of the mouth. Keep it light; do not replace it with an English r.",
        "drill": "Repeat rue, rouge, and voudrais slowly, then say the full phrase.",
    },
    {
        "id": "closed-e",
        "title": "Clear final e / e-acute",
        "triggers": {"cafe", "parle", "ete", "ecole", "repetez", "plait"},
        "content": "Keep final e-acute as a clear closed vowel and avoid an English diphthong. Example: cafe.",
        "drill": "Hold the final vowel briefly in cafe, then repeat the whole phrase.",
    },
    {
        "id": "liaison",
        "title": "Liaison and connected speech",
        "triggers": {"amis", "avez", "homme", "enfants", "avons", "deux", "nous"},
        "content": "In common vowel-initial word groups, a normally silent final consonant may link to the next word. Keep the group smooth, not rushed.",
        "drill": "Practise nous avons and deux amis as connected groups.",
    },
    {
        "id": "schwa",
        "title": "Schwa and unstressed syllables",
        "triggers": {"petite", "demain", "je", "le", "semaine", "revenir"},
        "content": "French unstressed e may be reduced in ordinary speech. Keep the phrase rhythm natural instead of stressing every syllable equally.",
        "drill": "Say je reviens in one smooth group, then add the surrounding words.",
    },
    {
        "id": "rhythm",
        "title": "French phrase rhythm",
        "triggers": {"rythme", "ensemble", "phrase", "parle", "visiterons"},
        "content": "French rhythm is organized around groups of syllables. Link words within a phrase and avoid giving every word a separate stress.",
        "drill": "Repeat the phrase in two smooth chunks with a small pause between them.",
    },
    {
        "id": "intonation",
        "title": "Phrase and question intonation",
        "triggers": {"intonation", "question", "comment", "allez-vous", "aujourd'hui"},
        "content": "French intonation depends on phrase type and context. A yes/no question often rises near the end; this app records pitch movement but does not score it as correct or incorrect.",
        "drill": "Say the question once with a gentle rise at the end, then once as a statement.",
    },
]


def normalize_text(value: str) -> str:
    """Normalize case and punctuation while preserving French accents."""
    value = unicodedata.normalize("NFKC", value).casefold().replace("’", "'")
    return " ".join(re.findall(r"[\wÀ-ÖØ-öø-ÿœæ]+(?:'[\wÀ-ÖØ-öø-ÿœæ]+)*", value))


def _fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


def word_errors(reference: str, transcript: str) -> dict[str, Any]:
    """Return transparent token-level substitutions, omissions, and insertions."""
    expected_display = normalize_text(reference).split()
    heard_display = normalize_text(transcript).split()
    expected = [_fold(word) for word in expected_display]
    heard = [_fold(word) for word in heard_display]
    matcher = SequenceMatcher(a=expected, b=heard, autojunk=False)
    substitutions: list[dict[str, Any]] = []
    omissions: list[dict[str, Any]] = []
    insertions: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            width = min(i2 - i1, j2 - j1)
            for offset in range(width):
                substitutions.append({"expected": expected_display[i1 + offset], "heard": heard_display[j1 + offset]})
            omissions.extend({"word": word} for word in expected_display[i1 + width:i2])
            insertions.extend({"word": word} for word in heard_display[j1 + width:j2])
        elif tag == "delete":
            omissions.extend({"word": word} for word in expected_display[i1:i2])
        elif tag == "insert":
            insertions.extend({"word": word} for word in heard_display[j1:j2])

    error_count = len(substitutions) + len(omissions) + len(insertions)
    word_count = len(expected)
    wer = error_count / max(word_count, 1)
    return {
        "reference_words": word_count,
        "spoken_words": len(heard),
        "substitutions": substitutions,
        "omissions": omissions,
        "insertions": insertions,
        "word_error_rate": round(wer, 4),
        "word_match_score": round(max(0.0, 100.0 * (1.0 - wer)), 1),
        "exact_match": expected == heard and bool(expected),
    }


def timing_metrics(segments: list[dict[str, Any]], transcript: str) -> dict[str, Any]:
    """Calculate observable timing features; these are not a fluency diagnosis."""
    words = [word for word in normalize_text(transcript).split() if word]
    timed_words = []
    segment_rows = []
    asr_logprobs = []
    no_speech = []
    for segment in segments or []:
        try:
            start, end = float(segment["start"]), float(segment["end"])
            if end >= start:
                segment_rows.append((start, end))
            if segment.get("avg_logprob") is not None:
                asr_logprobs.append(float(segment["avg_logprob"]))
            if segment.get("no_speech_prob") is not None:
                no_speech.append(float(segment["no_speech_prob"]))
            for word in segment.get("words", []) or []:
                timed_words.append((float(word["start"]), float(word["end"])))
        except (KeyError, TypeError, ValueError):
            continue

    spans = timed_words or segment_rows
    duration = max((end for _, end in spans), default=0.0) - min((start for start, _ in spans), default=0.0)
    pauses = [max(0.0, spans[index + 1][0] - spans[index][1]) for index in range(len(spans) - 1)]
    long_pauses = [pause for pause in pauses if pause >= 0.7]
    result: dict[str, Any] = {
        "speech_duration_seconds": round(duration, 2) if duration > 0 else None,
        "speaking_rate_words_per_minute": round(len(words) * 60 / duration, 1) if duration > 0 else None,
        "pause_count_over_0_7s": len(long_pauses),
        "longest_pause_seconds": round(max(long_pauses), 2) if long_pauses else 0.0,
        "timing_source": "Whisper word/segment timestamps" if spans else "unavailable",
        "fluency_interpretation": "Timing descriptors only; no validated fluency threshold is applied.",
    }
    if asr_logprobs:
        mean_logprob = sum(asr_logprobs) / len(asr_logprobs)
        result["asr_log_probability_mean"] = round(mean_logprob, 4)
        result["intelligibility_proxy"] = round(max(0.0, min(100.0, (mean_logprob + 1.0) * 100.0)), 1)
        result["intelligibility_note"] = "ASR confidence proxy, not a human intelligibility rating."
    if no_speech:
        result["no_speech_probability_mean"] = round(sum(no_speech) / len(no_speech), 4)
    return result


def assess_speech(reference: str, transcript: str, segments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    alignment = word_errors(reference, transcript)
    timing = timing_metrics(segments or [], transcript)
    return {**alignment, **timing}


def retrieve_guidance(reference: str, transcript: str, assessment: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    """Rank pronunciation notes by lexical cues in the actual target and errors."""
    target_words = {_fold(word) for word in normalize_text(reference).split()}
    spoken_words = {_fold(word) for word in normalize_text(transcript).split()}
    error_words: set[str] = set()
    for item in assessment.get("substitutions", []):
        error_words.update({_fold(item.get("expected", "")), _fold(item.get("heard", ""))})
    for kind in ("omissions", "insertions"):
        error_words.update(_fold(item.get("word", "")) for item in assessment.get(kind, []))
    ranked = []
    for item in KNOWLEDGE_BASE:
        triggers = {_fold(word) for word in item["triggers"]}
        overlap_target = len(triggers & target_words)
        overlap_error = len(triggers & error_words)
        overlap_spoken = len(triggers & spoken_words)
        score = 3 * overlap_error + 2 * overlap_target + overlap_spoken
        if score:
            ranked.append((score, item))

    if not ranked:
        fallback = next(item for item in KNOWLEDGE_BASE if item["id"] == "rhythm")
        ranked = [(0, fallback)]
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [
        {"id": item["id"], "title": item["title"], "content": item["content"], "drill": item["drill"], "relevance": score}
        for score, item in ranked[:limit]
    ]


def infer_rasa(ser_label: str, confidence: float) -> tuple[str, str]:
    """Map only the SER labels supported by the current checkpoint."""
    label = ser_label.casefold().strip()
    rasa = SER_RASA_MAP.get(label, "Shanta")
    source = "speech-model" if label in SER_RASA_MAP else "low-confidence-default"
    if confidence < 40:
        return "Shanta", "low-confidence-default"
    return rasa, source


def validate_rasa(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().casefold()
    for name in RASA_PROFILES:
        if name.casefold() == normalized:
            return name
    return None


def generate_grounded_feedback(
    reference: str,
    transcript: str,
    assessment: dict[str, Any],
    guidance: list[dict[str, Any]],
    rasa: str,
    rasa_source: str,
    feedback_style: str = "adaptive",
) -> dict[str, str]:
    """Generate deterministic feedback from retrieved notes and aligned errors."""
    profile = RASA_PROFILES[rasa]
    substitutions = assessment.get("substitutions", [])
    omissions = assessment.get("omissions", [])
    insertions = assessment.get("insertions", [])
    score = float(assessment.get("word_match_score", 0.0))

    if substitutions:
        first = substitutions[0]
        observation = f"I heard '{first['heard']}' where the target was '{first['expected']}'."
    elif omissions:
        observation = f"The transcript did not include '{omissions[0]['word']}' from the target."
    elif insertions:
        observation = f"The transcript included '{insertions[0]['word']}' beyond the target phrase."
    elif assessment.get("exact_match"):
        observation = "The transcript matches the target sentence. This checks words, not individual phonemes."
    else:
        observation = "The transcript is empty, so the sentence could not be compared."

    top = guidance[0]
    note = f"{top['title']}: {top['content']} Practice cue: {top['drill']}"
    if score < 60:
        label, timing = "Supportive practice", "After the recording"
    elif score < 90:
        label, timing = "Focused correction", "After the recording"
    else:
        label, timing = "Extension", "After the recording"

    tone = profile["tone"]
    if feedback_style == "supportive":
        tone = "supportive and encouraging"
    elif feedback_style == "direct":
        tone = "clear and direct"
    feedback = f"{tone.capitalize()} feedback: {observation} {note}"
    next_activity = profile["next"]
    if score < 60:
        next_activity = f"{profile['adaptation'].capitalize()}: {top['drill']}"
    elif score >= 90:
        next_activity = f"{profile['adaptation'].capitalize()}: {next_activity}"

    return {
        "feedback": feedback,
        "feedback_type": label,
        "feedback_timing": timing,
        "next_activity": next_activity,
        "rasa_adaptation": profile["adaptation"],
        "rasa_source": rasa_source,
        "knowledge_source": top["id"],
        "reference_sentence": reference,
        "transcript": transcript,
    }


def summarize_progress(records: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [float(record["pronunciation_score"]) for record in records]
    ordered = sorted(records, key=lambda record: record.get("created_at") or "")
    error_counts: dict[str, int] = {}
    for record in records:
        details = record.get("assessment_details") or {}
        for kind in ("substitutions", "omissions", "insertions"):
            for item in details.get(kind, []):
                token = item.get("expected") or item.get("word") or "unknown"
                error_counts[token] = error_counts.get(token, 0) + 1
    trend = None
    if len(scores) >= 2:
        trend = round(scores[-1] - scores[0], 1)
    return {
        "session_count": len(scores),
        "average_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "latest_score": scores[-1] if scores else 0,
        "score_change": trend,
        "scores": [
            {"score": float(record["pronunciation_score"]), "created_at": record.get("created_at")}
            for record in ordered[-10:]
        ],
        "recurring_errors": [
            {"word": word, "count": count}
            for word, count in sorted(error_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:5]
        ],
    }
