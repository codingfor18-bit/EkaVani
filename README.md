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

Open the Vite URL printed in the terminal. During local development, Vite proxies API requests to `http://127.0.0.1:8000`. Set `VITE_API_URL` in `frontend/.env` only when the frontend and backend are hosted separately.

## Database configuration

The default is `sqlite:///./ekavani.db`, created in the backend working directory. For PostgreSQL, install the included driver and set `DATABASE_URL`, for example:

```text
postgresql+psycopg://user:password@localhost:5432/ekavani
```

Copy `backend/.env.example` to `backend/.env` and set environment variables in your shell or hosting service. Do not use the example JWT key for deployment. The app currently creates tables on startup; use a migration tool before changing the deployed schema.

## Deploy the website online

The repository includes a Render Blueprint and Dockerfile that serve the built React site and FastAPI API from one URL. To deploy it:

1. Push this project to GitHub and connect the repository in Render with **New → Blueprint**.
2. Select the `render.yaml` Blueprint and create the `ekavani` service in Singapore.
3. When Render asks for `DATABASE_URL`, enter the pooled Neon `DATABASE_URL` from the project root `.env.local`. Render generates `JWT_SECRET_KEY` for the hosted app.
4. Wait for the service health check to pass, then open its `onrender.com` URL.

The app stores account and practice data in Neon; it does not need a local SQLite database when `DATABASE_URL` is set. The free Render web service sleeps after 15 minutes without traffic, so its first request after sleeping can take longer. Speech analysis is optional in this prototype; the hosted image uses the lightweight backend requirements, so audio analysis needs the additional packages in `backend/requirements-speech.txt` and a host with enough memory for the speech models.

## Scope and limitations

Practice history and progress are user-specific. Pronunciation scoring is currently transcript similarity, not phoneme-level pronunciation assessment. Emotion labels come from a general speech-emotion model and should be treated as an estimate. The frontend design is retained; the progress and history pages now use saved practice data.

## Reproducible ASR pilot

`whisper_cv_eval_seed42.py` runs the 25-clip French ASR evaluation with a fixed seed and utterance-level bootstrap confidence interval. The raw audio subset is not committed; obtain the French clips and `metadata.csv`, then run:

```powershell
python whisper_cv_eval_seed42.py --dataset-dir ..\french_dataset_50mb
```

Recorded run: `openai-whisper` 20250625, Whisper `base`, CPU, French decoding, beam size 5; seed 42; 10,000 bootstrap resamples. The supplied French folder contains 1,262 audio files and Common Voice-style metadata; its exact Common Voice release was not supplied. The random 25-clip sample contained 25 speakers and produced WER 40.17% (92 errors / 229 reference words), bootstrap 95% CI [32.62%, 48.47%]. A separate five-clip pilot produced WER 26.19%, CER 10.27%, and one exact transcript. These are small exploratory ASR results, not emotion-recognition or learner-outcome results. No emotion labels were supplied, so emotion accuracy and F1 are not reported.
