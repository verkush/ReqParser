from flask import Flask, render_template, request, redirect, jsonify, send_file
import pdfplumber
import pandas as pd
import re
import os
from datetime import datetime

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"
 
# GLOBAL STATE
cadence_requirements = {}   # cadence -> [requirements]
req_family_id = "REQ"
max_len = 0

CADENCE_HEADER = r"Cadence:\s*([0-9.]+)"
REQ_FAMILY = r"ID:\s*([A-Za-z0-9_\-]+)"
REQ_PATTERN = r"[^.?!]*\b(shall|should|must|will|need to|required to)\b[^.?!]*[.?!]"


def parse_pdf(path):
    global cadence_requirements, req_family_id, max_len

    text = ""

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"

    # requirement family id
    m = re.search(REQ_FAMILY, text)
    if m:
        req_family_id = m.group(1).strip()

    # split cadence sections
    parts = re.split(CADENCE_HEADER, text)  # ["before", cadence1, text1, cadence2, text2...]

    cadence_requirements = {}

    for i in range(1, len(parts), 2):
        cadence = parts[i].strip()
        block = parts[i + 1]

        reqs = re.findall(REQ_PATTERN, block, flags=re.IGNORECASE)

        cadence_requirements[cadence] = list(dict.fromkeys(reqs))  # dedupe

    max_len = max(len(v) for v in cadence_requirements.values()) if cadence_requirements else 0


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files["pdf"]
        path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(path)

        parse_pdf(path)

        return redirect("/")

    return render_template(
        "index.html",
        cadence_requirements=cadence_requirements,
        req_family=req_family_id,
        max_len=max_len
    )


@app.route("/update", methods=["POST"])
def update():
    global cadence_requirements
    cadence_requirements = request.json
    return jsonify({"status": "ok"})


@app.route("/chart-data")
def chart_data():
    return jsonify({
        "labels": list(cadence_requirements.keys()),
        "counts": [len(v) for v in cadence_requirements.values()]
    })


@app.route("/export")
def export():
    cadences = list(cadence_requirements.keys())
    max_rows = max(len(v) for v in cadence_requirements.values()) if cadences else 0

    rows = []
    rows.append(["Requirement ID"] + cadences)

    for i in range(max_rows):
        rid = f"{req_family_id}-{i+1:03}"
        row = [rid]

        for c in cadences:
            row.append(cadence_requirements[c][i] if i < len(cadence_requirements[c]) else "")

        rows.append(row)

    df = pd.DataFrame(rows)

    filename = f"requirements_{datetime.now().timestamp()}.xlsx"
    df.to_excel(filename, index=False, header=False)

    return send_file(filename, as_attachment=True)


if __name__ == "__main__":
    os.makedirs("uploads", exist_ok=True)
    app.run(debug=True)
