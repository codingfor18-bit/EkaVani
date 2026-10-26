# EkaVani

EkaVani is a French speaking-practice prototype with a FastAPI backend and React frontend. Accounts and analyzed practice sessions are stored in the configured database. Uploaded recordings are temporary and removed after analysis.

## Run locally on Windows

Open PowerShell in `EkaVani-final`.

### Backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-speech.txt
uvicorn app.main:app --reload --port 8000
```

The first speech analysis may download the Whisper and emotion models. Install FFmpeg and make sure `ffmpeg` is on PATH for Whisper audio decoding. The lightweight backend (auth, health, and database APIs) starts without the optional speech packages; the analysis endpoint explains if they are missing.

Check `http://127.0.0.1:8000/health` and API docs at `http://127.0.0.1:8000/docs`.

### Frontend

In another PowerShell window:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL printed in the terminal. The API URL defaults to `http://127.0.0.1:8000`; set `VITE_API_URL` in `frontend/.env` if needed.

## Database configuration

The default is `sqlite:///./ekavani.db`, created in the backend working directory. For PostgreSQL, install the included driver and set `DATABASE_URL`, for example:

```text
postgresql+psycopg://user:password@localhost:5432/ekavani
```

Copy `backend/.env.example` to `backend/.env` and set environment variables in your shell or hosting service. Do not use the example JWT key for deployment. The app currently creates tables on startup; use a migration tool before changing the deployed schema.

## Scope and limitations

Practice history and progress are user-specific. Pronunciation scoring is currently transcript similarity, not phoneme-level pronunciation assessment. Emotion labels come from a general speech-emotion model and should be treated as an estimate. The frontend design is retained; the progress and history pages now use saved practice data.

## Reproducible ASR pilot

`whisper_cv_eval_seed42.py` runs the 25-clip French ASR evaluation with a fixed seed and utterance-level bootstrap confidence interval. The raw audio subset is not committed; obtain the French clips and `metadata.csv`, then run:

```powershell
python whisper_cv_eval_seed42.py --dataset-dir ..\french_dataset_50mb
```

Recorded run: `openai-whisper` 20250625, Whisper `base`, CPU, French decoding, beam size 5; seed 42; 10,000 bootstrap resamples. The supplied French folder contains 1,262 audio files and Common Voice-style metadata; its exact Common Voice release was not supplied. The random 25-clip sample contained 25 speakers and produced WER 40.17% (92 errors / 229 reference words), bootstrap 95% CI [32.62%, 48.47%]. A separate five-clip pilot produced WER 26.19%, CER 10.27%, and one exact transcript. These are small exploratory ASR results, not emotion-recognition or learner-outcome results. No emotion labels were supplied, so emotion accuracy and F1 are not reported.
