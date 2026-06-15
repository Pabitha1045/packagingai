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
