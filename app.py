from datetime import datetime
from pathlib import Path
import json
import math
from collections import Counter
import re
import uuid

import cv2
import easyocr
import httpx
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from ultralytics import YOLO
from werkzeug.utils import secure_filename
import os

BASE_DIR = Path(__file__).resolve().parent
for env_path in (BASE_DIR / ".env", BASE_DIR / "models" / ".env"):
    if env_path.exists():
        load_dotenv(env_path)
load_dotenv()

UPLOAD_DIR = BASE_DIR / "static" / "uploads"
RESULT_DIR = BASE_DIR / "static" / "results"
MODEL_PATH = BASE_DIR / "models" / "best.pt"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "packaging-verification-dev-key")
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

model = None
reader = None

try:
    from supabase_client import (
        fetch_inspections,
        get_supabase_client,
        insert_inspection,
    )
    _SUPABASE_ENABLED = get_supabase_client() is not None
except Exception:
    fetch_inspections = None
    insert_inspection = None
    _SUPABASE_ENABLED = False


def get_model():
    global model
    if model is None:
        model = YOLO(str(MODEL_PATH))
    return model


def get_reader():
    global reader
    if reader is None:
        reader = easyocr.Reader(["en"])
    return reader


def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def summarize_inspections(records):
    statuses = Counter(record.get("status", "Unknown") for record in records)
    severities = Counter(record.get("severity", "unknown") for record in records)
    missing_checks = Counter()

    for record in records:
        checks = record.get("checks") or {}
        for check_name, passed in checks.items():
            if not passed:
                missing_checks[check_name] += 1

    return {
        "total_inspections": len(records),
        "status_counts": dict(statuses),
        "severity_counts": dict(severities),
        "missing_or_failed_checks": dict(missing_checks),
        "latest_records": records[:20],
    }


def generate_groq_report(records):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured in .env.")

    summary = summarize_inspections(records)
    prompt = (
        "Create a clear packaging quality inspection report from these inspection records. "
        "Explain the problems found up to now, likely causes, and practical technical fixes. "
        "Return only valid JSON using this exact structure: "
        '{"overview":"string","issues":[{"name":"string","count":1,"severity":"Low|Medium|High",'
        '"risk":"string"}],"recommended_fixes":[{"title":"string","details":["string"]}],'
        '"next_steps":["string"],"action_items":["string"],'
        '"timeline":[{"task":"string","duration":"string"}],"conclusion":"string"}. '
        "Do not use Markdown and do not mention any database, API provider, or AI vendor.\n\n"
        f"Inspection data JSON:\n{json.dumps(summary, default=str)}"
    )
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a quality-engineering analyst for an AI packaging verification system.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.25,
        "max_tokens": 1200,
    }
    try:
        with httpx.Client(trust_env=False, timeout=45) as client:
            response = client.post(
                GROQ_API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Groq API request failed: {exc.response.status_code} {exc.response.text}"
        ) from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Could not reach Groq API: {exc}") from exc

    content = data["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The report service returned an invalid report format.") from exc


def has_package_like_shape(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    h, w = image.shape[:2]

    lines = cv2.HoughLinesP(
        edges,
        1,
        math.pi / 180,
        threshold=80,
        minLineLength=min(h, w) // 4,
        maxLineGap=20,
    )

    if lines is None:
        return False

    left_vertical = 0
    right_vertical = 0
    top_horizontal = 0

    for line in lines[:, 0]:
        x1, y1, x2, y2 = map(int, line)
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)

        if dy > dx * 2:
            if min(x1, x2) < w * 0.25:
                left_vertical += 1
            if max(x1, x2) > w * 0.75:
                right_vertical += 1
        elif dx > dy * 2 and min(y1, y2) < h * 0.25:
            top_horizontal += 1

    return left_vertical > 0 and right_vertical > 0 and top_horizontal > 1


def parse_date(text):
    if not text:
        return None

    try:
        return datetime.strptime(text, "%d %b %Y")
    except ValueError:
        return None


def inspect_image(image_path, output_path):
    active_model = get_model()
    active_reader = get_reader()
    image = cv2.imread(str(image_path))

    if image is None:
        raise ValueError("Could not read the uploaded image.")

    results = active_model(image)
    checks = {
        "label": False,
        "barcode": False,
        "qr_code": False,
        "quantity": False,
        "mfg_date": False,
        "expiry_date": False,
        "damaged": False,
    }
    detections = []
    mfg_text = None
    expiry_text = None
    expired = False
    status = "PACKAGE OK"
    color = (0, 255, 0)

    for result in results:
        boxes = result.boxes.xyxy.cpu().numpy()
        classes = result.boxes.cls.cpu().numpy()
        confidences = result.boxes.conf.cpu().numpy()

        for box, cls, confidence in zip(boxes, classes, confidences):
            label = active_model.names[int(cls)]
            x1, y1, x2, y2 = map(int, box)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(image.shape[1], x2), min(image.shape[0], y2)

            detections.append(
                {
                    "label": label.replace("rotation", "").replace("_", " ").title(),
                    "confidence": round(float(confidence) * 100, 1),
                }
            )

            if label == "labelrotation":
                checks["label"] = True
            elif label == "barcoderotation":
                checks["barcode"] = True
            elif label == "qr_coderotation":
                checks["qr_code"] = True
            elif label == "quantityrotation":
                checks["quantity"] = True
            elif label == "damaged_labelrotation":
                checks["damaged"] = True
            elif label == "mfg_daterotation":
                checks["mfg_date"] = True
                crop = image[y1:y2, x1:x2]
                text_items = active_reader.readtext(crop, detail=0)
                for text in text_items:
                    match = re.search(r"\d{1,2}\s[A-Z]{3}\s\d{4}", text.upper())
                    if match:
                        mfg_text = match.group()
            elif label == "expiry_daterotation":
                checks["expiry_date"] = True
                crop = image[y1:y2, x1:x2]
                text_items = active_reader.readtext(crop, detail=0)
                for text in text_items:
                    match = re.search(r"\d{1,2}\s[A-Z]{3}\s\d{4}", text.upper())
                    if match:
                        expiry_text = match.group()

            cv2.rectangle(image, (x1, y1), (x2, y2), (24, 214, 146), 2)
            cv2.putText(
                image,
                label.replace("rotation", ""),
                (x1, max(25, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (24, 214, 146),
                2,
            )

    mfg_date = parse_date(mfg_text)
    expiry_date = parse_date(expiry_text)

    if expiry_date and mfg_date:
        if expiry_date < mfg_date:
            expired = True
            status = "INVALID DATE (EXPIRY BEFORE MFG)"
        elif expiry_date < datetime.today():
            expired = True
            status = "PRODUCT EXPIRED"

    if not checks["label"]:
        if has_package_like_shape(image):
            status = "LABEL IS MISSING"
            color = (0, 165, 255)
        else:
            status = "IMAGE IS NOT OF A LABEL"
            color = (0, 0, 255)
    elif checks["damaged"]:
        status = "DAMAGED LABEL"
        color = (0, 0, 255)
    elif expired:
        color = (0, 0, 255)
    elif not checks["expiry_date"]:
        status = "EXPIRY DATE MISSING"
        color = (0, 165, 255)
    elif not checks["mfg_date"]:
        status = "MFG DATE MISSING"
        color = (0, 165, 255)
    elif not checks["barcode"]:
        status = "BARCODE MISSING"
        color = (0, 165, 255)
    elif not checks["qr_code"]:
        status = "QR CODE MISSING"
        color = (0, 165, 255)
    elif not checks["quantity"]:
        status = "QUANTITY MISSING"
        color = (0, 165, 255)

    if status == "PACKAGE OK":
        color = (0, 255, 0)

    cv2.putText(
        image,
        status,
        (35, 58),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        color,
        3,
    )
    cv2.imwrite(str(output_path), image)

    severity = "pass" if status == "PACKAGE OK" else "warn"
    if "EXPIRED" in status or "INVALID" in status or "DAMAGED" in status or "NOT OF A LABEL" in status:
        severity = "fail"

    return {
        "status": status,
        "severity": severity,
        "checks": checks,
        "mfg_text": mfg_text or "Not detected",
        "expiry_text": expiry_text or "Not detected",
        "detections": detections,
        "detected_count": len(detections),
    }


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    report = None

    if request.method == "POST":
        uploaded_file = request.files.get("image")

        if not uploaded_file or uploaded_file.filename == "":
            flash("Please choose an image before starting inspection.")
            return redirect(url_for("index"))

        if not allowed_file(uploaded_file.filename):
            flash("Upload a JPG, PNG, WEBP, or BMP image.")
            return redirect(url_for("index"))

        safe_name = secure_filename(uploaded_file.filename)
        unique_name = f"{uuid.uuid4().hex}_{safe_name}"
        upload_path = UPLOAD_DIR / unique_name
        result_name = f"result_{Path(unique_name).stem}.jpg"
        result_path = RESULT_DIR / result_name

        uploaded_file.save(upload_path)

        try:
            result = inspect_image(upload_path, result_path)
        except Exception as exc:
            flash(f"Inspection failed: {exc}")
            return redirect(url_for("index"))

        result["uploaded_url"] = url_for("static", filename=f"uploads/{unique_name}")
        result["result_url"] = url_for("static", filename=f"results/{result_name}")

        # Persist inspection summary to Supabase (only metadata, not images)
        if _SUPABASE_ENABLED:
            try:
                record = {
                    "uploaded_filename": unique_name,
                    "uploaded_url": result.get("uploaded_url"),
                    "result_url": result.get("result_url"),
                    "status": result.get("status"),
                    "severity": result.get("severity"),
                    "checks": result.get("checks"),
                    "mfg_text": result.get("mfg_text"),
                    "expiry_text": result.get("expiry_text"),
                    "detections": result.get("detections"),
                    "detected_count": result.get("detected_count"),
                    "model_path": str(MODEL_PATH),
                }
                insert_inspection(record)
            except Exception as exc:  # don't break the request if DB fails
                app.logger.warning("Could not save inspection history: %s", exc)
                flash("The inspection completed, but its history could not be saved.")

    return render_template("index.html", result=result, report=report)


@app.route("/generate-report", methods=["POST"])
def generate_report():
    if not _SUPABASE_ENABLED or fetch_inspections is None:
        flash("Inspection history is not configured, so a report cannot be generated.")
        return redirect(url_for("index"))

    try:
        records = fetch_inspections(limit=50)
    except Exception as exc:
        app.logger.warning("Could not load inspection history: %s", exc)
        flash("Inspection history could not be loaded.")
        return redirect(url_for("index"))

    if not records:
        flash("No inspection history is available yet. Run at least one inspection first.")
        return redirect(url_for("index"))

    try:
        report = generate_groq_report(records)
    except Exception as exc:
        flash(f"Report generation failed: {exc}")
        return redirect(url_for("index"))

    return render_template(
        "index.html",
        result=None,
        report={
            **report,
            "record_count": len(records),
            "generated_at": datetime.now().strftime("%d %b %Y, %I:%M %p"),
        },
    )


if __name__ == "__main__":
    app.run(debug=True)
