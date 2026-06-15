# PackagingAI

PackagingAI is a Flask application that inspects package images using a trained
YOLO model and OCR. It checks labels, barcodes, QR codes, quantity, manufacturing
and expiry dates, and visible package damage. Inspection history can be stored
for structured quality reports.

## Setup

1. Create a Python virtual environment.
2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `models/.env` and add your credentials.
4. Create the inspection table using `db/create_table.sql`.
5. Start the app:

   ```powershell
   python app.py
   ```

6. Open `http://127.0.0.1:5000`.

The trained model is stored at `models/best.pt`. Uploaded and annotated images
are generated at runtime under `static/uploads` and `static/results`.

## Deploy On Render

Push this repository to GitHub, then create a new Render Web Service from the
repository.

Use these settings if Render does not auto-detect `render.yaml`:

- Runtime: `Python 3`
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn --bind 0.0.0.0:$PORT --timeout 180 --workers 1 app:app`

Add these environment variables in Render:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `GROQ_API_KEY`
- `GROQ_MODEL`, optional: `llama-3.1-8b-instant`
- `FLASK_SECRET_KEY`
- `FLASK_DEBUG`: `0`

Uploaded and annotated images are stored on the Render instance filesystem, so
they may reset when the service restarts. Inspection records are still saved in
the configured database.
