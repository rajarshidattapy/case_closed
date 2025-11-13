// =====================================================
// GLOBAL STATE (MAS-Compatible)
// =====================================================
const chatBox = document.querySelector('#chat-box');
const chatForm = document.querySelector('#chat-form');
const chatInput = document.querySelector('#chat-input');
const uploadBtn = document.querySelector('#upload-btn');
const pdfInput = document.querySelector('#pdf-input');
const analyzeBtn = document.querySelector('#analyze-btn');
const draftBtn = document.querySelector('#draft-btn');
const draftGenerateBtn = document.querySelector('#draft-generate-btn');
const roleSelectEl = document.querySelector('#role-select');

let contextId = null;
let currentAnalysis = {};
let currentCases = [];

document.addEventListener('DOMContentLoaded', async () => {
    await loadContext();
    setupTabs();
    setupEventListeners();
});

// =====================================================
// TAB SWITCHING
// =====================================================
function setupTabs() {
    const tabs = document.querySelectorAll('.panel-tab');
    const tabContents = document.querySelectorAll('.panel-tab-content');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.getAttribute('data-tab');

            tabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(tc => tc.classList.remove('active'));

            tab.classList.add('active');
            document.getElementById(`tab-${target}`).classList.add('active');
        });
    });
}

// =====================================================
// EVENT LISTENERS
// =====================================================
function setupEventListeners() {
    uploadBtn.addEventListener('click', () => pdfInput.click());
    pdfInput.addEventListener('change', handlePDFUpload);

    analyzeBtn.addEventListener('click', handleAnalyze);

    draftBtn.addEventListener('click', () =>
        document.querySelector('[data-tab="draft"]').click()
    );

    draftGenerateBtn.addEventListener('click', handleDraftGenerate);

    chatForm.addEventListener('submit', handleChatSubmit);

    chatInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });

    chatInput.addEventListener('input', autoResizeTextarea);
}

// =====================================================
// CONTEXT
// =====================================================
async function loadContext() {
    try {
        const res = await fetch('/context');
        const data = await res.json();

        contextId = data.context_id;

        if (data.context.analysis) updateAnalysisPanel(data.context.analysis);
        if (data.context.cases) updateCasesPanel(data.context.cases);

    } catch (err) {
        console.error("Context load failed:", err);
    }
}

// =====================================================
// UPLOAD PDF
// =====================================================
async function handlePDFUpload() {
    if (!pdfInput.files.length) return;
    const file = pdfInput.files[0];

    appendMessage('bot', `Uploading <b>${file.name}</b>...`);

    const formData = new FormData();
    formData.append('pdf', file);

    try {
        const res = await fetch('/upload', { method: 'POST', body: formData });
        const data = await res.json();

        if (data.error) return appendMessage('bot', `Error: ${data.error}`);

        appendMessage('bot', `Uploaded: <b>${data.filename}</b>`);
        appendMessage('bot', `<i>Extracted text:</i><br>${data.text}`);

        contextId = data.context_id;

        updateAnalysisPanel(data.analysis);
        document.querySelector('[data-tab="analysis"]').click();

    } catch (err) {
        appendMessage('bot', 'Upload failed.');
        console.error(err);
    }
}

// =====================================================
// ANALYZE
// =====================================================
async function handleAnalyze() {
    if (!contextId) return appendMessage('bot', "Start by uploading or describing your case.");

    appendMessage('bot', 'Analyzing case...');

    try {
        const res = await fetch('/analyze', {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ context_id: contextId })
        });

        const data = await res.json();
        if (data.error) return appendMessage('bot', `Error: ${data.error}`);

        updateAnalysisPanel(data.analysis);
        appendMessage('bot', "Analysis complete!");

        document.querySelector('[data-tab="analysis"]').click();

    } catch (err) {
        appendMessage('bot', "Analysis failed.");
        console.error(err);
    }
}

// =====================================================
// CHAT (MAS Pipeline)
// =====================================================
async function handleChatSubmit(e) {
    e.preventDefault();

    const message = chatInput.value.trim();
    if (!message) return;

    appendMessage('user', message.replace(/\n/g, '<br>'));
    chatInput.value = '';
    autoResizeTextarea();

    const thinking = appendMessage('bot', getThinkingText());

    try {
        const res = await fetch('/chat', {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message,
                context_id: contextId
            })
        });

        const data = await res.json();
        thinking.remove();

        // MAS STEP 1: Clarifying questions
        if (data.status === "clarifying") {
            let qTxt = "<b>I need more information:</b><br><br>";
            data.questions.forEach((q, i) => qTxt += `${i + 1}. ${q}<br>`);

            appendMessage('bot', qTxt);
            updateAnalysisPanel(data.analysis);

            return;
        }

        // MAS FINAL RESULT
        if (data.status === "results") {

            contextId = data.context_id;

            updateAnalysisPanel(data.analysis);

            if (data.cases.length > 0) {
                updateCasesPanel(data.cases);
                appendMessage('bot', `Found ${data.cases.length} relevant cases.`);
                document.querySelector('[data-tab="cases"]').click();
            } else {
                appendMessage('bot', "No relevant cases found.");
            }

            appendMessage('bot', "You can continue the conversation or generate a document.");

            return;
        }

        // Error
        if (data.status === "error") {
            appendMessage('bot', data.message);
        }

    } catch (err) {
        thinking.remove();
        appendMessage('bot', "Server error.");
        console.error(err);
    }
}

// =====================================================
// DRAFT GENERATION
// =====================================================
async function handleDraftGenerate() {
    if (!contextId) return appendMessage('bot', "Upload or describe your case first.");

    const docType = document.getElementById('draft-type').value;
    const draftContent = document.getElementById('draft-content');

    draftContent.innerHTML = '<p class="empty-state">Generating document...</p>';

    try {
        const res = await fetch('/draft', {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ context_id: contextId, doc_type: docType })
        });

        const data = await res.json();
        if (data.error) return draftContent.innerHTML = data.error;

        displayDraft(data.document);
        appendMessage('bot', `Generated your ${docType}! Check the Draft panel.`);

        document.getElementById('draft-download-btn').style.display = "none";

    } catch (err) {
        draftContent.innerHTML = "Draft generation failed.";
        console.error(err);
    }
}

// =====================================================
// ANALYSIS PANEL
// =====================================================
function updateAnalysisPanel(analysis) {
    const div = document.getElementById('analysis-content');

    if (!analysis || Object.keys(analysis).length === 0) {
        div.innerHTML = "<p class='empty-state'>No analysis available.</p>";
        return;
    }

    let html = "";

    const sections = {
        "Facts": analysis.facts,
        "Jurisdictions": analysis.jurisdictions,
        "Parties": analysis.parties ? analysis.parties.map(p => `${p.name} (${p.role})`) : [],
        "Legal Issues": analysis.legal_issues,
        "Causes of Action": analysis.causes_of_action
    };

    for (const [title, items] of Object.entries(sections)) {
        if (items && items.length > 0) {
            html += `<div class="analysis-section"> 
                        <h4>${title}</h4>
                        <ul>${items.map(i => `<li>${escapeHtml(i)}</li>`).join("")}</ul>
                    </div>`;
        }
    }

    if (!html) html = "<p class='empty-state'>No structured analysis extracted.</p>";

    div.innerHTML = html;
}

// =====================================================
// CASES PANEL
// =====================================================
function updateCasesPanel(cases) {
    const div = document.getElementById('cases-content');

    if (!cases || cases.length === 0) {
        div.innerHTML = "<p class='empty-state'>No cases found.</p>";
        return;
    }

    div.innerHTML = cases.map(c => `
        <div class="case-item">
            <div class="case-title">${escapeHtml(c.title)}</div>
            ${c.citation ? `<div class="case-citation">${escapeHtml(c.citation)}</div>` : ""}
            <div class="case-relevance">
                <span class="relevance-score relevance-${getRelevanceClass(c.relevance_score)}">
                    Relevance: ${c.relevance_score}%
                </span>
            </div>
            <div class="relevance-reason">${escapeHtml(c.relevance_reason)}</div>
            <div class="case-snippet">${escapeHtml(c.snippet)}</div>
            <a href="${c.pdf_link}" target="_blank">View Case →</a>
        </div>
    `).join("");
}

function getRelevanceClass(score) {
    if (score >= 70) return "high";
    if (score >= 40) return "medium";
    return "low";
}

// =====================================================
// DRAFT PANEL
// =====================================================
function displayDraft(text) {
    const div = document.getElementById("draft-content");

    let html = "<div class='draft-document'>";

    text.split("\n").forEach(line => {
        if (line.startsWith("**") && line.endsWith("**")) {
            html += `<h3>${escapeHtml(line.replace(/\*\*/g, ""))}</h3>`;
        } else {
            html += `<p>${escapeHtml(line)}</p>`;
        }
    });

    html += "</div>";
    div.innerHTML = html;
}

// =====================================================
// UTILITIES
// =====================================================
function appendMessage(sender, text) {
    const el = document.createElement('div');
    el.className = `message ${sender} fade-in`;
    el.innerHTML = text;
    chatBox.appendChild(el);
    chatBox.scrollTo({ top: chatBox.scrollHeight, behavior: 'smooth' });
    return el;
}

function escapeHtml(t) {
    const div = document.createElement('div');
    div.textContent = t;
    return div.innerHTML;
}

function autoResizeTextarea() {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 200) + "px";
}

function getThinkingText() {
    const opt = [
        "Thinking...", "Processing...", "Analyzing...",
        "Checking legal context...", "Synthesizing arguments...",
        "Working through the MAS pipeline..."
    ];
    return opt[Math.floor(Math.random() * opt.length)];
}
