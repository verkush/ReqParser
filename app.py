from flask import Flask, render_template, request, redirect, jsonify, send_file
import pdfplumber, pandas as pd, re, os, sqlite3
from datetime import datetime
import nltk
from nltk.tokenize import sent_tokenize

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"
DB = "requirements.db"

CADENCE_HEADER = r"Cadence:\s*([0-9.]+)"
REQ_FAMILY = r"Legacy GUID:\s*([A-Za-z0-9_\-]+)"
INFO_FLAG = r"Information only"
REQ_PATTERN = r"\b(shall|should|must|will|required)\b"

os.makedirs("uploads", exist_ok=True)


def db_conn():
    return sqlite3.connect(DB)


def init_db():
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        req_family TEXT,
        type TEXT,
        cadence TEXT,
        description TEXT,
        priority TEXT,
        owner TEXT,
        status TEXT,
        module TEXT,
        UNIQUE(req_family,cadence,description)
    )""")
    con.commit()
    con.close()


init_db()


def parse_pdf(path):
    text = ""
    with pdfplumber.open(path) as pdf:
        for p in pdf.pages:
            t = p.extract_text()
            if t:
                text += t + "\n"

    fam = re.search(REQ_FAMILY, text)
    fam = fam.group(1) if fam else "REQ"

    info = bool(re.search(INFO_FLAG, text, re.IGNORECASE))

    parts = re.split(CADENCE_HEADER, text)

    rows = []

    for i in range(1, len(parts), 2):
        cadence = parts[i].strip()
        block = parts[i + 1]

        sentences = sent_tokenize(block)

        for s in sentences:
            if re.search(REQ_PATTERN, s, re.IGNORECASE):
                clean = " ".join(s.split())

                rows.append({
                    "req_family": fam,
                    "type": "Information only" if info else "Requirement",
                    "cadence": cadence,
                    "description": clean
                })

    return rows


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        files = request.files.getlist("pdf")

        for f in files:
            path = os.path.join(app.config["UPLOAD_FOLDER"], f.filename)
            f.save(path)

            items = parse_pdf(path)

            con = db_conn()
            cur = con.cursor()
            for r in items:
                try:
                    cur.execute("""INSERT OR IGNORE INTO requirements 
                    (req_family,type,cadence,description,priority,owner,status,module)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (r["req_family"],r["type"],r["cadence"],r["description"],"", "", "", ""))
                except:
                    pass
            con.commit()
            con.close()

        return redirect("/")

    con = db_conn()
    df = pd.read_sql_query("SELECT * FROM requirements", con)
    con.close()

    if df.empty:
        rows = []
    else:
        cadences = sorted(df["cadence"].unique().tolist())
        rows = []
        sno = 1
        seen = set()

        for _, r in df.iterrows():
            dup = (r["description"].lower(), r["cadence"])
            is_duplicate = dup in seen
            seen.add(dup)

            row = {
                "S.No.": sno,
                "Requirement ID": r["req_family"],
                "Type": r["type"],
                "Priority": r["priority"],
                "Owner": r["owner"],
                "Status": r["status"],
                "Module": r["module"],
                "duplicate": is_duplicate
            }

            for c in cadences:
                row[c] = r["description"] if r["cadence"] == c else ""

            rows.append(row)
            sno += 1

    return render_template("index.html", rows=rows)


@app.route("/update", methods=["POST"])
def update():
    data = request.json
    con = db_conn()
    cur = con.cursor()

    cur.execute("""UPDATE requirements 
    SET priority=?, owner=?, status=?, module=? 
    WHERE description=?""",
    (data["priority"],data["owner"],data["status"],data["module"],data["description"]))

    con.commit()
    con.close()
    return jsonify({"status": "ok"})


@app.route("/export/excel")
def export_excel():
    con = db_conn()
    df = pd.read_sql_query("SELECT * FROM requirements", con)
    con.close()
    file = f"requirements_{datetime.now().timestamp()}.xlsx"
    df.to_excel(file, index=False)
    return send_file(file, as_attachment=True)


@app.route("/export/csv")
def export_csv():
    con = db_conn()
    df = pd.read_sql_query("SELECT * FROM requirements", con)
    con.close()
    file = f"requirements_{datetime.now().timestamp()}.csv"
    df.to_csv(file, index=False)
    return send_file(file, as_attachment=True)


@app.route("/chart-data")
def chart_data():
    con = db_conn()
    df = pd.read_sql_query("SELECT cadence FROM requirements", con)
    con.close()

    counts = df["cadence"].value_counts()
    return jsonify({"labels": counts.index.tolist(), "counts": counts.values.tolist()})


if __name__ == "__main__":
    app.run(debug=True)
