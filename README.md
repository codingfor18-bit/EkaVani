# EkaVani

EkaVani is a French speaking-practice app with a React frontend and FastAPI backend. It transcribes French audio, compares the transcript with a practice sentence, retrieves pronunciation guidance, and stores practice results in PostgreSQL.

## Current project status

- The app is configured to use Neon PostgreSQL through `DATABASE_URL`. The backend health check and a practice-history save/read round trip were verified against Neon.
- The deployment configuration and app changes are pushed to the `deploy/render-neon` branch of [codingfor18-bit/EkaVani](https://github.com/codingfor18-bit/EkaVani).
- A successful Render deployment has not yet been confirmed. The Docker image has not been locally built because Docker was unavailable in the development environment.

## Run locally on Windows

Run commands from the repository root unless a command says otherwise. The backend loads `DATABASE_URL` from the root `.env.local` created by Neon. Keep this file private and out of Git.

### Install and start the backend

```powershell
py -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-speech.txt
$env:PYTHONPATH = 'backend'
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Install FFmpeg and ensure `ffmpeg` is on `PATH`. Whisper and the emotion model may download their model weights on first use. Check the API at `http://127.0.0.1:8000/health` and its documentation at `http://127.0.0.1:8000/docs`.

### Start the frontend

In a second PowerShell window:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open the Vite URL printed in the terminal. Vite proxies API requests to `http://127.0.0.1:8000`. The production build is served by FastAPI from the same origin.

## French practice levels and audio

Open **Practice**, choose one of the six custom difficulty groups, then choose a sentence. The checked-in French practice dataset at `backend/app/data/french_practice_sentences.json` has 10 prompts per group. It uses the order requested for this app: **A1 is hardest, then A2, B1, B2, C1, and C2 is easiest**. This reverses standard CEFR ordering. The source text you supplied labels A1 as beginner and C2 as mastery, so its sentences are remapped: source C2 sentences appear under app A1; source A1 sentences appear under app C2. The API also accepts a level filter, for example `/api/v1/practice/sentences?level=C2`.

For the selected sentence, record with the microphone or upload one audio clip (`.wav`, `.mp3`, `.m4a`, `.ogg`, or `.webm`) at a time. You can submit multiple attempts and try different sentences. Each attempt is analyzed and saved separately in Feedback History and My Progress. Audio is limited to 15 MB per attempt and is deleted from the server after analysis.

## Database and secrets

The app reads `DATABASE_URL` from the environment, root `.env.local`, root `.env`, or `backend/.env`. The deployed service requires `DATABASE_URL` and is configured for Neon PostgreSQL. It fails at startup if the deployment has no database URL. When a URL is configured, account and practice data go to that database; SQLite is only a fallback for local development without a configured database.

Do not commit `.env.local`, database credentials, or JWT secrets. Render generates `JWT_SECRET_KEY` from `render.yaml`. The app creates tables on startup and includes a small compatibility update for the assessment JSON column; use a migration tool for future schema changes.

## Deploy to Render

The repository includes `render.yaml` and a Dockerfile that builds the React site and serves it with FastAPI. To deploy:

1. In Render, connect the GitHub repository and select branch `deploy/render-neon`.
2. Create the service using the repository's Blueprint (`render.yaml`).
3. Set the `DATABASE_URL` secret to the pooled Neon connection string. Do this in Render's environment settings; never commit or paste the value into source files. Render generates the JWT secret.
4. Wait for the `/health` check, open the site URL, then try an audio upload and confirm it appears in Feedback History.

The Blueprint uses Render's free web-service plan, which may not have enough memory for Whisper and the emotion model together. Speech weights download on first use, and the free service may sleep when idle. If model inference runs out of memory on Render, use an instance with more memory. Docker was not available locally, so the container build still needs verification by Render.

## How speech assessment and feedback work

- **ASR:** Whisper transcribes French audio.
- **Transcript comparison:** Word alignment reports substitutions, omissions, insertions, word error rate (WER), character error rate (CER), and word precision, recall, and F1. Per-attempt metrics compare Whisper's transcript to the selected practice sentence. They measure text recognition, not phoneme-level pronunciation or accent quality.
- **Speech descriptors:** Word timing, pauses, pitch movement, and Whisper confidence are reported as observable features. They are not validated fluency, prosody, or human intelligibility scores.
- **Emotion:** The SUPERB speech-emotion checkpoint predicts four labels (happy, angry, sad, neutral). It does not classify all nine Navarasas. Learners can self-select one of nine rasa profiles to adapt feedback tone and next-practice suggestions.
- **Retrieval-grounded feedback:** The backend ranks a curated French pronunciation knowledge base using the selected sentence and aligned word errors, then uses retrieved guidance in deterministic feedback templates. This is not LLM-generated feedback.
- **Learning history:** Accounts, sessions, feedback, and progress are stored in the configured database. Learner preferences are stored in that learner's browser.

## Run backend tests and frontend build

From the repository root:

```powershell
$env:PYTHONPATH = 'backend'
backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
npm.cmd run build
```

The API integration test uses a stubbed speech recognizer and a temporary SQLite test database. Separately, the real Whisper and emotion checkpoints were exercised through the running API with a temporary test account and a silence recording; the result round-tripped through Neon history, and the temporary account and session were deleted. That smoke test checks inference and persistence wiring, not speech-recognition quality.

## Exploratory French ASR evaluation

The local sibling folder `../french_dataset_50mb` contains 1,262 French MP3 clips with reference sentences in `metadata.csv`; audio is kept outside Git. `whisper_cv_eval_seed42.py` evaluates a seeded sample against those references, calculates WER, CER, micro word precision/recall/F1, and a bootstrap WER confidence interval, and writes the latest summary to `backend/app/data/asr_benchmark.json`. The Settings page displays that corpus benchmark. Run from the project root:

```powershell
python whisper_cv_eval_seed42.py --dataset-dir ..\french_dataset_50mb
```

Latest recorded run: `openai-whisper` 20250625, Whisper `base`, CPU, French decoding, beam size 5; seed 42; 10,000 bootstrap resamples. On 25 randomly selected clips from 25 speakers, WER was 39.91% (85 errors / 213 reference words; bootstrap 95% CI 33.18%-47.09%), micro word precision 63.64%, recall 65.73%, F1 64.67%, and CER 16.41%. This is a small ASR transcript benchmark, not a learner pronunciation score or emotion-recognition score. The dataset has no emotion labels, so emotion-classification F1 cannot be calculated.
