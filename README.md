# Case Closed

Case Closed is a Flask-based demo app that showcases a multi-agent legal research pipeline driven by large language models and CourtListener. The UI is a chat-style web app where users can upload PDFs, describe fact patterns, and run a multi-step pipeline that extracts facts, generates search queries, retrieves and scores cases, and (optionally) drafts memos or briefs.

This README was updated to match the current `app.py` and `static/script.js` in this repository. It documents the endpoints the frontend expects, environment variables, how to run the app locally (Windows PowerShell-oriented), and quick usage notes.

## What the app provides (high level)

- A chat-like web UI (templates in `templates/`, client code in `static/script.js`).
- PDF upload and text extraction (PDF -> text via `pdfminer.six`).
- A multi-agent orchestration pipeline (implemented in `app.py`) that can:
  - ask clarifying questions,
  - extract structured information (facts, parties, issues, jurisdictions),
  - summarize the situation,
  - generate targeted search keywords,
  - query CourtListener for candidate cases,
  - score candidate cases for relevance,
  - draft memos/briefs (draft endpoint is present but the handler is a small stub in the current codebase).

## Important files

- `app.py` — Flask server, agent classes, and the orchestrator pipeline.
- `static/script.js` — Frontend logic (upload, chat, analyze, draft flow). The script expects the following endpoints: `/upload`, `/chat`, `/analyze` (frontend tries to call this), `/draft`, and `/context`.
- `templates/chat.html` — Main chat UI used by the app.
- `requirements.txt` — Python dependencies used by the project.

## Environment variables

Create a `.env` file in the project root with at least the following variables:

- `FLASK_SECRET_KEY` — Flask secret key (any string for development).
- `OPENAI_API_KEY` — Your OpenAI API key used by the HTTP client in `app.py`.
- `COURTLISTENER_TOKEN` — (optional) token for CourtListener API if you have one; the app will work without it but authenticated endpoints may offer higher rate limits.
- `HOST`, `PORT`, `DEBUG` — optional runtime configuration used by `app.py`.

Example `.env` (do NOT check secrets into source control):

```
FLASK_SECRET_KEY=your-secret
OPENAI_API_KEY=sk-...
COURTLISTENER_TOKEN=
HOST=0.0.0.0
PORT=5000
DEBUG=True
```

## Dependencies

Primary dependencies are listed in `requirements.txt`. Key packages the app relies on:

- Flask
- requests
- python-dotenv
- pdfminer.six (text extraction)
- openai (optional if you switch from the included HTTP wrapper)

Install them with:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Running locally (development)

1. Ensure your `.env` is in the project root and contains `OPENAI_API_KEY` and `FLASK_SECRET_KEY`.
2. Activate your virtual environment (example shown above) and install requirements.
3. Run the app:

```powershell
# from project root
python app.py
```

4. Open your browser to `http://localhost:5000`.

## Frontend behavior / usage

- Upload a PDF: click the upload button in the UI and select a PDF. The frontend POSTs to `/upload` (form field name `pdf`). The server extracts text and returns a preview and `context_id` used for the session.
- Chat: type a message and send. The frontend sends `{ message, context_id }` to `/chat`. The `/chat` route in `app.py` runs the full MAS pipeline (clarification, analysis, summary, query generation, CourtListener search, scoring) and returns a JSON response with `status`, `summary`, `analysis`, `cases`, `keywords`, and `context_id`.
- Analyze button (UI): the frontend calls `/analyze` with `{ context_id }` to request a focused analysis step. Note: in the current `app.py` some routes are implemented as part of the orchestrator while `POST /analyze` is expected by `static/script.js` — if you get 404 for `/analyze`, use the chat flow which triggers the same pipeline via `/chat`.
- Draft generation: the frontend calls `POST /draft` with `{ context_id, doc_type }`. In the present codebase, the `/draft` handler exists but is a minimal stub; it is wired in `script.js` and will return whatever the server-side draft logic produces (or an error if unimplemented).
- Context endpoint: the UI calls `GET /context` to load the current session context (analysis, cases, context_id). In the current `app.py` the `context` route is present but may be an empty stub — if it returns incomplete data, the UI will still function while using `context_id` returned from `/upload` or `/chat`.

## Endpoints summary

- `GET /` — serves the chat UI (`templates/chat.html`).
- `POST /upload` — multipart/form-data with `pdf` file; returns extracted text preview and `context_id`.
- `POST /chat` — JSON { message, context_id? }; runs the full pipeline and returns analysis, summary, and candidate cases.
- `POST /analyze` — JSON { context_id } (frontend expects this; may be missing as a separate route in server). If not present, use `/chat`.
- `POST /draft` — JSON { context_id, doc_type } to generate a memo or brief (stubbed/implemented depending on code).
- `GET /context` — returns the stored context for the user session (context_id, analysis, cases, etc.).

## Notes for developers

- Some server routes in the current `app.py` are partially implemented (placeholders/stubs) — check `app.py` for TODOs and omitted code markers. The orchestrator and agent classes are a good starting point if you want to flesh out separate `/analyze` and `/draft` handlers.
- The app currently uses a small HTTP OpenAI client inside `app.py`. You can replace it with the official `openai` library if desired; if you do, remember to update `requirements.txt` and how the client is initialized.
- Keep your `.env` and API keys private. Avoid committing the `.env` file to public repos.

## Security & rate limits

- CourtListener has rate limits and may require a token for higher throughput. Set `COURTLISTENER_TOKEN` in `.env` if you have one.
- OpenAI keys are sensitive — do not commit them. For larger usage consider server-side usage controls and request quotas.

## Troubleshooting

- If the UI shows errors when clicking Analyze or Draft, check your Flask server logs — some routes are intentionally left as minimal stubs while the MAS pipeline runs via `/chat`.
- If PDF extraction fails, ensure `pdfminer.six` is installed and that the uploaded file is a valid PDF.

## Contributing

Feel free to open issues or PRs to fix the analyze/draft routes, improve the frontend behavior, or add tests.

---

If you want, I can also:

- implement the missing `/analyze` route to match the frontend expectations,
- flesh out the `/draft` handler to return a sample generated document, or
- add a small test script that posts a sample PDF and prints the pipeline output.

Tell me which you'd like next and I will implement it.
