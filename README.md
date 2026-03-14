# intentions.ai — Proactive Browser Assistant

> Gemini Live Agent Challenge — UI Navigator category

Watches your active browser tab via screenshots, uses Gemini 2.0 Flash multimodal vision to infer your intent, and surfaces relevant information **before you ask** — as floating cards in the bottom-right corner of every page.

**Demo scenario:** User opens the USCIS biometrics rescheduling page → the assistant surfaces community insights about wait times. User selects "San Francisco" → the assistant surfaces nearby points of interest and practical logistics.

---

## Architecture

![intentions.ai — Architecture & Data Flow](live_architecture.png)

---

## How It Works

The extension runs entirely passively — no button to click, no query to type.

1. On every tab switch, page load, or significant DOM mutation, `background.js` captures a screenshot of the active tab
2. It bundles the screenshot with the page URL, title, optional geolocation, and up to 5 recent browsing history entries, then POSTs to `/analyze`
3. **Vision** (`vision.py`) — Gemini 2.0 Flash sees the screenshot and returns `{ intent, page_state, confidence }`
4. If `confidence >= 0.3`, the **ADK agent** (`agent.py`) uses `google_search` to find relevant information and returns up to 3 cards
5. Cards are forwarded to `content.js` and rendered as dismissable tiles bottom-right. Dismissed cards don't reappear for that URL

Triggers that fire an analysis:
- Tab activated or switched
- Page load completes (`status === "complete"`)
- DOM mutations settle (debounced 1.5s) — catches form interactions and SPA navigation
- Alarm poll (every ~1 minute)

Skipped automatically: `chrome://` pages, `chrome-extension://` pages, and pages where the screenshot hash hasn't changed since the last send.

---

## Quickstart

### 1. Clone and load the extension

```bash
git clone https://github.com/likhitjuttada/intentions.ai.git
cd intentions.ai
```

Open `extension/background.js` and set line 4:
```js
const BACKEND_URL = "https://YOUR_CLOUD_RUN_URL";
```

Then:
1. Open `chrome://extensions/`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked** → select the `extension/` folder
4. Any time you change `BACKEND_URL`, click the **reload icon** on the extension card for the change to take effect

Navigate to any public webpage — tiles appear bottom-right within ~5 seconds if Gemini infers your intent with `confidence >= 0.3`. On blank tabs, `chrome://` pages, or ambiguous pages, nothing is shown.

### 2. Backend (local dev only)

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
echo "GOOGLE_API_KEY=your-key-here" > .env
uvicorn main:app --reload --port 8080
```

---

## Testing Against Cloud Run

Replace `YOUR_CLOUD_RUN_URL` with your deployed service URL in all commands below.

### 1. Health check
```bash
curl https://YOUR_CLOUD_RUN_URL/health
```
Expected:
```json
{"status":"ok"}
```

### 2. Full pipeline — real page context

This sends a 1×1 PNG with a realistic URL. Vision will return low confidence on a blank image, but it confirms the full pipeline (API key → vision → confidence check → response) is working:

```bash
curl -s -X POST https://YOUR_CLOUD_RUN_URL/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "screenshot": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    "url": "https://my.uscis.gov/appointments/biometrics",
    "title": "USCIS - Reschedule Biometrics Appointment"
  }'
```

Expected shape (confidence may vary):
```json
{
  "intent": "...",
  "page_state": "...",
  "confidence": 0.3,
  "cards": []
}
```

### 3. With geolocation and history context

```bash
curl -s -X POST https://YOUR_CLOUD_RUN_URL/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "screenshot": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    "url": "https://my.uscis.gov/appointments/biometrics",
    "title": "USCIS - Reschedule Biometrics Appointment",
    "geolocation": { "lat": 37.7749, "lng": -122.4194 },
    "recent_history": [
      { "url": "https://reddit.com/r/USCIS", "title": "USCIS wait times", "visitCount": 3 }
    ]
  }'
```

### 4. Low-confidence short-circuit

Send a blank URL with no title — confidence should come back below 0.3 and `cards` should be `[]` with the agent never called:

```bash
curl -s -X POST https://YOUR_CLOUD_RUN_URL/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "screenshot": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    "url": "about:blank",
    "title": ""
  }'
```

Expected: `"cards": []`

### 5. Extension end-to-end

1. Load the extension with `BACKEND_URL` pointing to your Cloud Run URL
2. Open DevTools → **Application** → **Service Workers** (or click "service worker" link in `chrome://extensions/`)
3. Navigate to `https://my.uscis.gov` or any complex public page
4. Within ~5 seconds, check the **Console** tab in the service worker DevTools — you should see a successful POST to `/analyze`
5. Tiles appear bottom-right if the agent returns cards

---

## Deploy to Cloud Run

### Prerequisites
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed and authenticated
- A GCP project with billing enabled
- Gemini API key stored in Secret Manager as `google-api-key`

### One-time setup

```bash
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  containerregistry.googleapis.com secretmanager.googleapis.com

# Store API key
echo -n "YOUR_GEMINI_API_KEY" | gcloud secrets create google-api-key --data-file=-

# Grant Cloud Build access to the secret
PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding google-api-key \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### Build and deploy

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=COMMIT_SHA=$(git rev-parse --short HEAD)
```

### Get your Cloud Run URL

```bash
gcloud run services describe ui-navigator-backend \
  --region us-central1 \
  --format 'value(status.url)'
```

Set this URL as `BACKEND_URL` in `extension/background.js` and reload the extension.

---

## API Reference

### `GET /health`

```json
{"status": "ok"}
```

### `POST /analyze`

**Request:**
```json
{
  "screenshot": "<base64 PNG>",
  "url": "https://my.uscis.gov/...",
  "title": "USCIS - Reschedule Appointment",
  "geolocation": { "lat": 37.7749, "lng": -122.4194 },
  "recent_history": [
    { "url": "https://reddit.com/r/USCIS", "title": "USCIS tips", "visitCount": 2 }
  ]
}
```

`geolocation` and `recent_history` are optional — omitting them degrades card relevance but doesn't break anything.

**Response:**
```json
{
  "intent": "rescheduling a USCIS biometrics appointment",
  "page_state": "User is on the appointment selection form, no city selected yet",
  "confidence": 0.92,
  "cards": [
    {
      "id": "uscis-reschedule-tips",
      "title": "USCIS Biometrics Rescheduling Tips",
      "summary": "Reddit users report slots open Tues mornings. Bring original appointment notice + ID.",
      "icon": "📋",
      "link": "https://reddit.com/r/USCIS"
    }
  ]
}
```

If `confidence < 0.3`, `cards` is `[]` and the ADK agent is never called.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Chrome Extension | Manifest V3, vanilla JS |
| Backend | Python FastAPI on Cloud Run |
| Vision | Gemini 2.0 Flash (multimodal — screenshot → intent) |
| Agent | Google ADK (`google-adk`) with `google_search` tool |
| CI/CD | Cloud Build (`cloudbuild.yaml`) |
| Secrets | Google Secret Manager |

---

## File Structure

```
intentions.ai/
├── extension/
│   ├── manifest.json      # MV3 manifest — permissions: tabs, scripting, history, alarms, geolocation
│   ├── background.js      # service worker — screenshot capture, history, backend calls
│   ├── content.js         # overlay tile system — render, dismiss, DOM mutation detection
│   └── overlay.css        # tile styles
├── backend/
│   ├── main.py            # FastAPI /health + /analyze endpoints
│   ├── vision.py          # Gemini 2.0 Flash: screenshot → { intent, page_state, confidence }
│   ├── agent.py           # ADK root agent: intent → google_search → cards[]
│   └── requirements.txt
├── Dockerfile
├── cloudbuild.yaml
└── README.md
```

---

## Hackathon Compliance

- **Gemini multimodal** — `vision.py` sends the raw PNG screenshot to `gemini-2.0-flash`; intent is inferred visually, not from DOM scraping
- **Google ADK** — `agent.py` uses `google-adk` `Agent` + `Runner` with the built-in `google_search` tool
- **Google Cloud Run** — `Dockerfile` + `cloudbuild.yaml` deploy to Cloud Run in `us-central1`
- **Secret Manager** — API key injected at runtime via `--update-secrets`, never baked into the image
