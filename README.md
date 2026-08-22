# ⚖️ EloJudge — Production Feedback Prioritization Engine

> **Turn messy user feedback into a prioritized, explainable backlog using Swiss tournament Elo ratings, dynamic rubric synthesis, and auditable decision receipts.**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Google Gemini](https://img.shields.io/badge/Google%20Gemini-3.6%20Flash%20%2F%20Pro-8E75B2.svg?logo=google&logoColor=white)](https://ai.google.dev/)
[![DigitalOcean PostgreSQL](https://img.shields.io/badge/DigitalOcean-PostgreSQL%2018-0080FF.svg?logo=digitalocean&logoColor=white)](https://www.digitalocean.com/products/managed-databases-postgresql)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🌟 Overview

Product managers and founders often receive hundreds of unstructured feedback items — bugs, feature requests, minor styling tweaks, and spam. Scoring them sequentially with LLMs is expensive, inconsistent, and produces arbitrary scores without explanations.

**EloJudge** reimagines backlog prioritization as a **Swiss-system tournament**:
1. **Cleans & clusters** messy requests locally with zero API cost.
2. **Synthesizes a custom multi-dimensional rubric** tailored to quarterly product goals.
3. **Pits candidate items head-to-head** in balanced tournament rounds judged by Google Gemini.
4. **Calculates mathematically stable Elo skill ratings** with verifiable win/loss receipts.
5. **Assigns delivery roadmap tiers** (**Now / Next / Later**) with full Markdown & CSV exports.

---

## 📐 Judgment Pipeline Flowchart

```mermaid
flowchart TD
    %% Styling
    classDef input fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef stage fill:#0b111e,stroke:#2dd4bf,stroke-width:2px,color:#f8fafc;
    classDef router fill:#1e1b4b,stroke:#a78bfa,stroke-width:2px,color:#f8fafc;
    classDef db fill:#022c22,stroke:#34d399,stroke-width:2px,color:#f8fafc;
    classDef output fill:#14532d,stroke:#4ade80,stroke-width:2px,color:#f8fafc;

    subgraph Inputs ["1. Ingestion & Authentication"]
        A1["Raw User Feedback (CSV / JSON / Text)"]:::input
        A2["Product Context & Goals"]:::input
        AuthCheck{"User Auth Check\n(Google OAuth / BYOK)"}:::router
        A1 & A2 --> AuthCheck
    end

    subgraph Preprocessing ["2. Local Cleaning & Pre-Ranking"]
        B1["Local Cleaner & Normalizer\n• Unicode cleanup\n• Spam / junk filter\n• SequenceMatcher deduplication"]:::stage
        B2["TF-IDF Keyword & Severity Scorer\n• Bug / Crash / Security boost\n• Frequency weight aggregation"]:::stage
        B3["Top 8 Contenders Selected\n(Lower items routed to Later backlog)"]:::stage
        AuthCheck -->|Authenticated| B1
        B1 --> B2 --> B3
    end

    subgraph RubricGen ["3. Product Rubric Synthesis"]
        C1{"Rubric Cache\nHit?"}:::router
        C2["Generate Calibrated Rubric via Gemini\n• 4-5 Weighted criteria\n• Tailored to product goals"]:::stage
        C3[("PostgreSQL\nrubric_cache")]:::db
        B3 --> C1
        C1 -->|Miss| C2 --> C3
        C1 -->|Hit| C4["Calibrated Scoring Rubric"]:::stage
        C3 -.-> C4
        C2 --> C4
    end

    subgraph Tournament ["4. Swiss Head-to-Head Tournament"]
        D1["Swiss Pairing Engine\n• Equal score pairings\n• Avoid rematch duplicates"]:::stage
        D2{"Obvious Pair\nHeuristic?"}:::router
        D3["Deterministic Local Rule\n(Severity disparity / score gap)"]:::stage
        D4{"Judgment\nCache Hit?"}:::router
        D5[("PostgreSQL\njudgment_cache")]:::db
        D6["Model Router\n• High stakes → Gemini 3.6 Pro\n• Standard → Gemini 3.6 Flash"]:::router
        D7["Batched Pairwise LLM Judgment\n• 2 pairs / request\n• Strict JSON receipts"]:::stage
        D8["Fallback Local Judge\n(Graceful recovery)"]:::stage
        D9["Elo Rating Update\n• K-factor = 24\n• Expected score vs actual"]:::stage
        D10{"Early Stopping\nCheck\n(Tiers converged?)"}:::router

        C4 --> D1
        D1 --> D2
        D2 -->|Yes| D3 --> D9
        D2 -->|No| D4
        D4 -->|Hit| D9
        D4 -->|Miss| D6
        D6 --> D7 --> D9
        D7 -.->|Timeout / Error| D8 --> D9
        D7 --> D5
        D9 --> D10
        D10 -->|More rounds needed| D1
    end

    subgraph Finalization ["5. Delivery Tiers & Storage"]
        E1["Delivery Tier Partitioning\n• NOW (Top 2-3 & Critical)\n• NEXT (Middle tier)\n• LATER (Lower priority clusters)"]:::output
        E2["Token & Cost Accounting\n(Budget & telemetry receipts)"]:::stage
        E3[("DigitalOcean PostgreSQL\n• ranking_jobs\n• user_usage_log")]:::db
        E4["Interactive Backlog Arena UI\n• Match receipts & why-details\n• Markdown / CSV export\n• Shareable job receipt"]:::output

        D10 -->|Tournament converged| E1
        E1 --> E2 --> E3 --> E4
    end
```

---

## 🚀 Key Architectural Features

| Feature | Description | Benefit |
| :--- | :--- | :--- |
| **🧹 Zero-Cost Local Cleaning** | Cleans unicode, strips noise/spam, and merges near-duplicate requests using TF-IDF and sequence matching before hitting LLMs. | Saves 60-80% of unnecessary API tokens. |
| **📐 Dynamic Rubric Synthesis** | Analyzes product context to formulate 4-5 weighted evaluation criteria (e.g. *User Retention*, *Revenue Impact*, *Dev Feasibility*). | Objective, tailored criteria for every product domain. |
| **⚔️ Swiss Tournament Engine** | Non-elimination pairwise tournament matching items with similar Elo ratings across $R = \lceil\log_2 N\rceil + 1$ rounds. | Fair comparisons with minimum $O(N \log N)$ match complexity. |
| **📊 Explainable Elo Ratings** | Calculates skill ratings ($K=24$) with auditable reason logs and exact head-to-head win/loss receipts. | Every decision has proof of why feature A beat feature B. |
| **🛡️ Hybrid Router & Caching** | Local rule engine catches obvious pairs; order-independent caching prevents duplicate LLM comparisons. | Sub-second latency on repeated comparisons. |
| **🔑 Auth & BYOK Rate Limits** | Google Identity OAuth (5 free runs/day) + Bring-Your-Own-Key (BYOK) for unlimited runs. | Secure multi-tenant usage with abuse protection. |
| **🗄️ DigitalOcean PostgreSQL** | Persistent storage for job receipts, user quota logs, and long-term rubric/judgment cache. | Survives restarts with full run history API. |

---

## 🛠️ Technology Stack

- **Backend:** [FastAPI](https://fastapi.tiangolo.com) (Python 3.11+), [Pydantic v2](https://docs.pydantic.dev/), [Uvicorn](https://www.uvicorn.org/)
- **AI Models:** Google Gemini 3.6 Flash (fast pairwise judger) & Gemini 3.6 Pro (rubric synthesis and tie-breakers) via the official `google-genai` SDK
- **Database:** Managed [DigitalOcean PostgreSQL 18](https://www.digitalocean.com/products/managed-databases-postgresql) with connection pooling via `asyncpg`
- **Frontend:** Single-page Vanilla HTML5/CSS3/ES6+ with Space Grotesk/Inter typography, dark glassmorphism aesthetic, and zero heavy build frameworks
- **Testing:** `pytest` + `pytest-anyio` (80+ automated unit & integration tests)

---

## ⚡ Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/89Aman/Elojudge.git
cd Elojudge
```

### 2. Set Up Virtual Environment & Dependencies
```bash
python -m venv .venv
# On Linux/macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Configure Environment Variables
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=your_gemini_api_key_here
MODEL=gemini-3.6-flash
MODEL_STRONG=gemini-3.6-pro

# Google OAuth (Optional for guest BYOK, required for Google sign-in)
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret

# DigitalOcean Managed PostgreSQL
DATABASE_URL=postgresql://doadmin:your_password@your-do-host:25060/defaultdb?sslmode=require
```

### 4. Run the Local Development Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Visit `http://localhost:8000` in your browser. Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

### 5. Run Test Suite
```bash
pytest
```

---

## 📡 API Reference

### `POST /rank`
Runs the complete 8-step Swiss tournament feedback prioritization pipeline.

**Request Body:**
```json
{
  "product_context": "QuickNote is a student note-taking app focused on speed and exam prep.",
  "feedback_items": [
    "Add dark mode",
    "Export notes to PDF",
    "Crash on launch with iOS 18",
    "Add tags and nested folders",
    "Sync notes via Google Drive"
  ],
  "max_candidates": 8,
  "user_api_key": "optional_custom_gemini_key",
  "google_id_token": "optional_google_jwt"
}
```

**Response Snapshot:**
```json
{
  "job_id": "job_a1b2c3d4e5f6",
  "rubric": {
    "dimensions": [
      { "name": "Exam Preparation Value", "weight": 0.35, "description": "..." },
      { "name": "App Stability & Friction", "weight": 0.30, "description": "..." }
    ]
  },
  "summary": {
    "raw_items": 5,
    "unique_clusters": 5,
    "rounds": 4,
    "pairwise_comparisons": 8,
    "estimated_cost": 0.00042
  },
  "ranked_items": [
    {
      "rank": 1,
      "id": "c1",
      "text": "Crash on launch with iOS 18",
      "elo": 1342.5,
      "tier": "Now",
      "reasons": ["Critical stability bug blocking core student workflow..."],
      "beaten_items": ["Add dark mode", "Export notes to PDF"]
    }
  ]
}
```

### Additional Endpoints
- `GET /health` — Service liveness and configured model status.
- `GET /auth/status` — Inspect remaining daily free runs and OAuth configuration.
- `GET /history` — List recent backlog prioritization runs.
- `GET /history/{job_id}` — Retrieve a full historical backlog receipt.
- `GET /demo-data` — QuickNote sample product context and feedback items.

---

## 🐳 Docker Deployment

```bash
# Build the image
docker build -t elojudge:latest .

# Run container
docker run -p 8080:8080 --env-file .env elojudge:latest
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
