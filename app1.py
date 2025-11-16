import os
import tempfile
import requests
import uuid
import re
import json

from flask import Flask, request, jsonify, render_template, session
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from pdfminer.high_level import extract_text

# =====================================================
# LOAD ENVIRONMENT
# =====================================================
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
COURTLISTENER_TOKEN = os.getenv("COURTLISTENER_TOKEN")

# =====================================================
# OPENROUTER RAW HTTP CLIENT
# =====================================================

class OpenRouterHTTPClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.url = "https://openrouter.ai/api/v1/chat/completions"

    def chat(self, model, messages, temperature=0):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }

        r = requests.post(self.url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()

        return data["choices"][0]["message"]["content"]


# Global OpenRouter client
client = OpenRouterHTTPClient(OPENROUTER_API_KEY)


# =====================================================
# FLASK INIT
# =====================================================
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")
app.config["UPLOAD_FOLDER"] = tempfile.gettempdir()
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {"pdf"}


# =====================================================
# AGENT FOUNDATION
# =====================================================

DEFAULT_MODEL = "google/gemma-3-27b-it:free"

class Agent:
    """Base class for all agents."""
    def __init__(self, name, role_description, model=DEFAULT_MODEL):
        self.name = name
        self.role = role_description
        self.model = model
        self.memory = []  # Agent-level memory (local only)

    def ask(self, prompt):
        messages = [{"role": "system", "content": self.role}]

        for m in self.memory:
            messages.append({"role": "assistant", "content": m})

        messages.append({"role": "user", "content": prompt})

        try:
            answer = client.chat(
                model=self.model,
                messages=messages,
                temperature=0
            )
            self.memory.append(answer)
            return answer

        except Exception as e:
            return f"[Agent {self.name} Error: {e}]"


# =====================================================
# 6 LEGAL AGENTS
# =====================================================

class ClarifierAgent(Agent):
    def __init__(self):
        super().__init__(
            "clarifier",
            (
                "You are a legal paralegal. Ask up to 3 clarifying questions "
                "ONLY about missing essential legal facts. "
                "If enough info exists, reply EXACTLY: NO QUESTIONS NEEDED."
            )
        )

class AnalyzerAgent(Agent):
    def __init__(self):
        super().__init__(
            "analyzer",
            (
                "You analyze legal text and extract structured information. "
                "Return JSON strictly:\n"
                "{\n"
                '  "facts": [],\n'
                '  "jurisdictions": [],\n'
                '  "parties": [],\n'
                '  "legal_issues": [],\n'
                '  "causes_of_action": [],\n'
                '  "penal_codes": []\n'
                "}"
            )
        )

class SummarizerAgent(Agent):
    def __init__(self):
        super().__init__(
            "summarizer",
            "You summarize legal situations concisely and factually."
        )

class QueryAgent(Agent):
    def __init__(self):
        super().__init__(
            "query_generator",
            "You output EXACTLY 5 legal search keywords (no numbering, no extra text)."
        )

class ScorerAgent(Agent):
    def __init__(self):
        super().__init__(
            "scorer",
            (
                "You evaluate relevance of cases. Return JSON only:\n"
                '{"score": <0-100>, "reason": "<1 sentence>"}'
            )
        )

class DrafterAgent(Agent):
    def __init__(self):
        super().__init__(
            "drafter",
           (
                "You draft legal memos/briefs using facts, issues, and cases. "
                "Write professionally, structured, concise."
            )
        )


# =====================================================
# ORCHESTRATOR — SAME AS ORIGINAL PIPELINE
# =====================================================

class LegalOrchestrator:
    def __init__(self):
        self.clarifier = ClarifierAgent()
        self.analyzer = AnalyzerAgent()
        self.summarizer = SummarizerAgent()
        self.query = QueryAgent()
        self.scorer = ScorerAgent()
        self.drafter = DrafterAgent()

    # Step 1 — Clarify
    def clarify(self, text):
        return self.clarifier.ask(f"Case description:\n{text}")

    # Step 2 — Structured extraction
    def analyze(self, text):
        raw = self.analyzer.ask(text)
        try:
            return json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        except:
            return {
                "facts": [], "jurisdictions": [], "parties": [],
                "legal_issues": [], "causes_of_action": [], "penal_codes": []
            }

    # Step 3 — Summarize
    def summarize(self, text):
        return self.summarizer.ask(text)

    # Step 4 — 5 keywords
    def generate_query(self, summary, analysis):
        prompt = f"Summary:\n{summary}\nAnalysis:\n{json.dumps(analysis)}"
        return self.query.ask(prompt)

    # Step 5 — CourtListener search
    def courtlistener_search(self, keywords):
        url = "https://www.courtlistener.com/api/rest/v4/search/"
        headers = {}

        if COURTLISTENER_TOKEN:
            headers["Authorization"] = f"Token {COURTLISTENER_TOKEN}"

        def _build_params(keywords, page=1, page_size=10, court=None, court_id=None,
                          start_date=None, end_date=None, extra_filters=None):
            params = {
                "q": keywords,
                "page": page,
                "page_size": page_size
            }

            if court:
                params["court"] = court
            if court_id:
                params["court__id"] = court_id

            if start_date:
                params["decision_date__gte"] = start_date
            if end_date:
                params["decision_date__lte"] = end_date

            if extra_filters and isinstance(extra_filters, dict):
                params.update(extra_filters)

            return params

        if isinstance(keywords, dict):
            k = keywords.get("q") or ""
            page = keywords.get("page", 1)
            page_size = keywords.get("page_size", 10)
            court = keywords.get("court")
            court_id = keywords.get("court_id")
            start_date = keywords.get("start_date")
            end_date = keywords.get("end_date")
            extra_filters = keywords.get("extra_filters")
            params = _build_params(k, page, page_size, court, court_id, start_date, end_date, extra_filters)
        else:
            params = _build_params(keywords)

        try:
            r = requests.get(url, params=params, headers=headers, timeout=20)
            r.raise_for_status()
            data = r.json()
        except requests.exceptions.RequestException as e:
            return [{"title": "CourtListener error", "snippet": str(e), "pdf_link": "", "citation": "", "decision_date": ""}]

        results = []
        for item in data.get("results", []):
            title = item.get("caseName") or item.get("name") or "Untitled"
            citation = item.get("citation", "")
            pdf_link = item.get("absolute_url", "")

            if pdf_link.startswith("/"):
                pdf_link = "https://www.courtlistener.com" + pdf_link

            results.append({
                "title": title,
                "citation": citation,
                "snippet": item.get("snippet", ""),
                "pdf_link": pdf_link,
                "decision_date": item.get("decision_date", "")
            })

        return results

    # Step 6 — Scoring
    def score_case(self, summary, case):
        prompt = f"""
Summary:
{summary}

Case Title: {case['title']}
Snippet: {case['snippet']}

Return JSON.
"""
        raw = self.scorer.ask(prompt)
        try:
            parsed = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            parsed["score"] = max(0, min(100, int(parsed["score"])))
            return parsed
        except:
            return {"score": 50, "reason": "Parsing error"}

    # Step 7 — Draft memo/brief
    def draft_document(self, context, doc_type="memo"):
        prompt = f"Draft a {doc_type} using:\n{json.dumps(context, indent=2)}"
        return self.drafter.ask(prompt)


# =====================================================
# CONTEXT MGMT
# =====================================================

user_contexts = {}

def get_context_id():
    if "context_id" not in session:
        session["context_id"] = str(uuid.uuid4())
    return session["context_id"]


# =====================================================
# ROUTES
# =====================================================

@app.route("/")
def index():
    return render_template("chat.html")


# -----------------------------------------------------
# PDF UPLOAD
# -----------------------------------------------------
def allowed_file(fname):
    return "." in fname and fname.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/upload", methods=["POST"])
def upload():
    if "pdf" not in request.files:
        return jsonify({"error": "No PDF uploaded"}), 400

    f = request.files["pdf"]

    if f.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(f.filename):
        return jsonify({"error": "Invalid file type"}), 400

    fname = secure_filename(f.filename)
    path = os.path.join(app.config["UPLOAD_FOLDER"], fname)
    f.save(path)

    try:
        pdf_text = extract_text(path)
        if not pdf_text.strip():
            pdf_text = f"[PDF {fname} uploaded but no extractable text]"
    except Exception as e:
        pdf_text = f"[PDF parsing error: {e}]"

    context_id = get_context_id()
    ctx = user_contexts.setdefault(context_id, {
        "text": "",
        "analysis": {},
        "summary": "",
        "cases": [],
        "queries": []
    })

    ctx["text"] += "\n\n" + pdf_text

    return jsonify({
        "status": "uploaded",
        "text": pdf_text[:500] + "..." if len(pdf_text) > 500 else pdf_text,
        "context_id": context_id
    })


# -----------------------------------------------------
# MAIN CHAT — FULL MAS PIPELINE
# -----------------------------------------------------
@app.route("/chat", methods=["POST"])
def chat():
    message = request.json.get("message", "").strip()

    if not message:
        return jsonify({"error": "empty message"}), 400

    context_id = get_context_id()
    ctx = user_contexts.setdefault(context_id, {
        "text": "",
        "analysis": {},
        "summary": "",
        "cases": [],
        "queries": []
    })

    ctx["text"] += "\n\n" + message

    orchestrator = LegalOrchestrator()

    # STEP 1 — Clarify
    clarification = orchestrator.clarify(ctx["text"])
    if "NO QUESTIONS NEEDED" not in clarification.upper():
        return jsonify({
            "status": "clarifying",
            "questions": clarification.split("\n"),
            "context_id": context_id
        })

    # STEP 2 — Analyze
    analysis = orchestrator.analyze(ctx["text"])
    ctx["analysis"] = analysis

    # STEP 3 — Summarize
    summary = orchestrator.summarize(ctx["text"])
    ctx["summary"] = summary

    # STEP 4 — Keywords
    keywords = orchestrator.generate_query(summary, analysis)
    ctx["queries"].append(keywords)

    # STEP 5 — CourtListener search
    cases = orchestrator.courtlistener_search(keywords)

    # STEP 6 — Score
    scored = []
    for c in cases:
        result = orchestrator.score_case(summary, c)
        c["relevance_score"] = result["score"]
        c["relevance_reason"] = result["reason"]
        scored.append(c)

    scored.sort(key=lambda x: x["relevance_score"], reverse=True)
    ctx["cases"] = scored

    return jsonify({
        "status": "results",
        "summary": summary,
        "analysis": analysis,
        "cases": scored,
        "keywords": keywords,
        "context_id": context_id
    })


# -----------------------------------------------------
# DRAFT
# -----------------------------------------------------
@app.route("/draft", methods=["POST"])
def draft():
    context_id = request.json.get("context_id")
    doc_type = request.json.get("doc_type", "memo")

    ctx = user_contexts.get(context_id)
    if not ctx:
        return jsonify({"error": "Context not found"}), 404

    orchestrator = LegalOrchestrator()
    document = orchestrator.draft_document(ctx, doc_type)

    return jsonify({
        "status": "success",
        "document": document,
        "context_id": context_id
    })


# -----------------------------------------------------
# GET CONTEXT
# -----------------------------------------------------
@app.route("/context", methods=["GET"])
def context():
    context_id = get_context_id()
    return jsonify({
        "context_id": context_id,
        "context": user_contexts.get(context_id, {})
    })


# =====================================================
# RUN SERVER
# =====================================================
if __name__ == "__main__":
    print("\n🎯 AI Legal Multi-Agent Assistant running…")
    app.run(host="0.0.0.0", port=5000, debug=True)
