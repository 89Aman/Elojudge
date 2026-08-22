"""EloJudge — Production Feedback Prioritization Engine.

Cleans messy user feedback locally, generates a calibrated product rubric,
executes a Swiss head-to-head model comparison tournament, and computes
explainable Elo ratings with auditable decision logs.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.auth import rate_limiter, verify_google_id_token
from app.budget import JobBudget
from app.cleaner import clean_feedback
from app.config import settings
from app.database import (
    close_db,
    get_job_by_id,
    get_recent_jobs,
    init_db,
    record_user_usage_in_db,
    save_ranking_job,
)
from app.demo_data import DEMO_FEEDBACK_ITEMS, DEMO_PRODUCT_CONTEXT
from app.judge import judge_pairs
from app.observability import ObservabilityTracker
from app.preprocess import pre_rank_clusters
from app.rubric import generate_rubric
from app.schemas import (
    LowerPriorityItem,
    PipelineSummary,
    RankedItem,
    RankRequest,
    RankResponse,
)
from app.tournament import (
    apply_match_result,
    assign_tiers,
    check_early_stopping,
    compute_num_rounds,
    generate_pairings,
    init_candidates,
    rank_candidates,
)

# ── Logging Configuration ────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d — %(message)s",
)
logger = logging.getLogger("elojudge")


# ── Application Lifespan & Service Health Checks ─────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown event management with multi-service diagnostics."""
    logger.info("=" * 72)
    logger.info("⚡ ELOJUDGE BACKEND INITIALIZATION & SERVICE HEALTH DIAGNOSTICS")
    logger.info("=" * 72)

    # 1. AI/LLM Service Check
    if settings.api_key:
        logger.info(
            "🤖 [Service: AI Engine] READY | Fast: %s | Strong: %s | Key: Configured",
            settings.model_cheap,
            settings.model_strong,
        )
    else:
        logger.warning(
            "⚠️ [Service: AI Engine] NO SERVER KEY | Fast: %s | Strong: %s | (Users must provide BYOK key)",
            settings.model_cheap,
            settings.model_strong,
        )

    # 2. Database Service Check
    if settings.database_url:
        logger.info("🗄️ [Service: Database] DigitalOcean PostgreSQL target configured: %s...", settings.database_url[:32])
    else:
        logger.info("ℹ️ [Service: Database] In-memory standalone mode (DATABASE_URL not set)")
    await init_db()

    # 3. Auth & Rate Limiter Service Check
    if settings.google_client_id:
        logger.info("🔑 [Service: Google Auth] OAuth Client ID configured (%s...)", settings.google_client_id[:16])
    else:
        logger.info("ℹ️ [Service: Google Auth] Google OAuth not configured")
    logger.info("🛡️ [Service: Rate Limiter] Active (5 free daily runs/user, BYOK unlimited)")

    # 4. Static Frontend Assets Check
    static_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    index_exists = os.path.exists(os.path.join(static_path, "index.html"))
    logger.info("🎨 [Service: Frontend UI] Static Dark Arena Assets: %s (path=%s)", "LOADED" if index_exists else "MISSING", static_path)
    logger.info("=" * 72)

    yield

    logger.info("🛑 EloJudge backend shutting down...")
    await close_db()
    logger.info("✅ All services stopped cleanly.")


# ── OpenAPI Metadata ─────────────────────────────────────────────────────────

API_DESCRIPTION = """
## ⚖️ EloJudge API

**EloJudge** turns raw, unstructured user feedback into an actionable, explainable product backlog.

### 🌟 Key Capabilities:
* **🧹 Local Cleaning & TF-IDF Deduplication**: Filters spam, noise, and clusters near-duplicates before any API calls.
* **📐 Dynamic Rubric Synthesis**: Generates weighted scoring criteria tailored to product goals.
* **⚔️ Swiss Head-to-Head Tournament**: Competes top candidates in balanced rounds.
* **📊 Elo Rating Computation**: Computes stable skill ratings and assigns **Now / Next / Later** delivery tiers.
* **🛡️ Production Resilience**: In-memory rate limiting, Google OAuth verification, and Bring-Your-Own-Key (BYOK) support.
"""

TAGS_METADATA = [
    {
        "name": "Feedback Prioritization",
        "description": "Core 8-stage Swiss tournament ranking and rubric synthesis pipeline.",
    },
    {
        "name": "Auth & Rate Limits",
        "description": "Google Identity authentication and daily quota status inspection.",
    },
    {
        "name": "Demo & Utility",
        "description": "Sample datasets and health monitoring endpoints.",
    },
]

app = FastAPI(
    title="EloJudge API",
    description=API_DESCRIPTION,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    contact={
        "name": "EloJudge Team",
        "url": "https://github.com/89Aman/Elojudge",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# ── Middleware ───────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """HTTP request diagnostic logging middleware."""
    start_time = time.time()
    path = request.url.path
    method = request.method
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "127.0.0.1")

    try:
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000.0
        # Don't flood logs with static asset queries unless error
        if not path.startswith("/static/") or response.status_code >= 400:
            logger.info("📡 [%s] %s -> %d (%.1fms) [client=%s]", method, path, response.status_code, duration_ms, client_ip)
        return response
    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000.0
        logger.error("💥 [%s] %s -> 500 Server Error (%.1fms): %s", method, path, duration_ms, exc)
        raise exc


# ── Custom Error Page Templates ──────────────────────────────────────────────

ERROR_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — EloJudge</title>
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#05070d;color:#e9eef7;font-family:'Inter',sans-serif;}}
.err-wrap{{text-align:center;max-width:480px;padding:40px 32px;background:rgba(15,22,34,0.72);
border:1px solid rgba(148,163,184,0.12);border-radius:20px;backdrop-filter:blur(16px);
box-shadow:0 20px 44px -8px rgba(0,0,0,0.65);}}
.err-code{{font-family:'Space Grotesk',sans-serif;font-size:5rem;font-weight:700;
background:linear-gradient(135deg,#2dd4bf,#8b5cf6);-webkit-background-clip:text;
-webkit-text-fill-color:transparent;background-clip:text;line-height:1;margin:0 0 8px;}}
.err-title{{font-size:1.4rem;font-weight:600;margin:0 0 12px;}}
.err-msg{{color:#97a3ba;font-size:0.95rem;line-height:1.6;margin:0 0 28px;}}
.err-btn{{display:inline-block;padding:12px 28px;background:linear-gradient(135deg,#0f766e,#2dd4bf);
color:#05070d;font-weight:700;border-radius:999px;text-decoration:none;font-size:0.95rem;
transition:transform 0.15s,box-shadow 0.15s;}}
.err-btn:hover{{transform:translateY(-2px);box-shadow:0 6px 24px rgba(45,212,191,0.35);}}
</style></head><body><div class="err-wrap">
<p class="err-code">{code}</p>
<h1 class="err-title">{title}</h1>
<p class="err-msg">{message}</p>
<a href="/" class="err-btn">← Back to EloJudge</a>
</div></body></html>"""


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Any) -> HTMLResponse:
    """Render dark arena error page for unmatched endpoints."""
    return HTMLResponse(
        ERROR_PAGE_TEMPLATE.format(
            code="404",
            title="Page not found",
            message=f"The route <strong>{request.url.path}</strong> does not exist. Return home to prioritize your backlog.",
        ),
        status_code=status.HTTP_404_NOT_FOUND,
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc: Any) -> HTMLResponse:
    """Render dark arena error page for unhandled internal exceptions."""
    return HTMLResponse(
        ERROR_PAGE_TEMPLATE.format(
            code="500",
            title="Internal Server Error",
            message="An unexpected error occurred during processing. Please verify server logs and API configurations.",
        ),
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


# ── Static File Mount & Single Page Application ──────────────────────────────

static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve favicon directly for browser standard requests."""
    icon_file = os.path.join(static_dir, "favicon.svg")
    if os.path.exists(icon_file):
        return FileResponse(icon_file, media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="Favicon not found")


@app.get("/", summary="Web Application Entrypoint", include_in_schema=False)
async def root():
    """Serve the single-page web application frontend."""
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"status": "ok", "service": "EloJudge", "version": "1.0.0"}


# ── Health & Utility Endpoints ───────────────────────────────────────────────

@app.get(
    "/health",
    tags=["Demo & Utility"],
    summary="Health Check Status",
    response_description="System operational status",
)
async def health():
    """Verify backend service liveness and current deployment version."""
    return {
        "status": "healthy",
        "service": "EloJudge API",
        "version": "1.0.0",
        "model_configured": settings.model,
    }


@app.get(
    "/demo-data",
    tags=["Demo & Utility"],
    summary="Sample QuickNote Dataset",
    response_description="Pre-packaged product context and raw feedback items",
)
async def get_demo_data():
    """Provide reference demonstration dataset for quick testing and onboarding."""
    return {
        "product_context": DEMO_PRODUCT_CONTEXT,
        "feedback_items": DEMO_FEEDBACK_ITEMS,
    }


# ── Authentication & Rate Limiting Endpoints ─────────────────────────────────

@app.get(
    "/auth/status",
    tags=["Auth & Rate Limits"],
    summary="Check User Quota & Authentication State",
    response_description="Current user profile, daily run balance, and quota cap",
)
async def auth_status(request: Request, google_id_token: str = ""):
    """Inspect caller quota allocation based on IP address or Google ID token.

    - **Anonymous / Guest**: 2 free runs / day (IP-based).
    - **Google Sign-In**: 5 free runs / day (email-based).
    - **Custom Key (BYOK)**: Unlimited runs.
    """
    user_info = await verify_google_id_token(google_id_token) if google_id_token else None
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "127.0.0.1")
    identifier = user_info["email"] if user_info else client_ip
    is_google = bool(user_info)
    remaining = rate_limiter.get_remaining(identifier, is_google_user=is_google)

    return {
        "authenticated": is_google,
        "user": user_info,
        "remaining_runs": remaining,
        "max_runs": 5 if is_google else 0,
        "login_required": not is_google and not bool(request.headers.get("x-gemini-api-key")),
        "google_client_id": settings.google_client_id,
    }


# ── Main Ranking Pipeline ───────────────────────────────────────────────────

@app.post(
    "/rank",
    response_model=RankResponse,
    tags=["Feedback Prioritization"],
    summary="Execute Feedback Prioritization Pipeline",
    response_description="Complete explainable backlog, rubric dimensions, tournament match history, and token telemetry.",
    responses={
        200: {"description": "Successfully ranked feedback with full match receipts."},
        400: {"description": "Validation error or fewer than 2 distinct items after local cleaning."},
        401: {"description": "Authentication required. User must sign in with Google or supply a custom API key."},
        429: {"description": "Daily free run limit reached (5/5 runs). Prompted to add Bring-Your-Own-Key."},
    },
)
async def rank_feedback(request: RankRequest, raw_request: Request):
    """Execute complete 8-step production-aware ranking pipeline.

    ### Pipeline Stages:
    1. **Local Cleaning**: Unicode normalizer, spam rejection, and SequenceMatcher clustering.
    2. **Rubric Synthesis**: Dynamic weighted criteria generated from product goals and cached.
    3. **Pre-Ranking**: Deterministic keyword and severity scoring to select top 8 tournament contenders.
    4. **Swiss Pairing**: Pair candidate items avoiding duplicate matches across rounds.
    5. **Pairwise Judging**: Batched model evaluation with order-independent caching and router heuristics.
    6. **Elo Mathematics**: Rating adjustments per match with K-factor = 24.
    7. **Tier Categorization**: Now, Next, Later delivery tier partitioning.
    8. **Telemetry Accounting**: Cost estimation, token counters, and latency logs.
    """
    # ── Rate Limiting & User Auth Check ──────────────────────────────────────
    client_ip = raw_request.headers.get("x-forwarded-for", raw_request.client.host if raw_request.client else "127.0.0.1")
    user_info = await verify_google_id_token(request.google_id_token) if request.google_id_token else None
    identifier = user_info["email"] if user_info else client_ip
    is_google = bool(user_info)
    has_custom_key = bool(request.user_api_key and len(request.user_api_key.strip()) > 10)

    # Enforce mandatory login if no BYOK key
    if not is_google and not has_custom_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign-in required: Please sign in with Google (top right) or add your Gemini API Key in Settings (🔑) to run EloJudge.",
        )

    allowed, remaining, limit_msg = rate_limiter.check_and_record(
        identifier=identifier,
        is_google_user=is_google,
        has_custom_key=has_custom_key,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=limit_msg,
        )

    active_api_key = request.user_api_key.strip() if has_custom_key else None

    # ── 0. Initialize Budget & Telemetry ─────────────────────────────────────
    budget = JobBudget()
    if request.budget:
        if request.budget.max_llm_requests:
            budget.max_llm_requests = request.budget.max_llm_requests
        if request.budget.max_input_tokens:
            budget.max_input_tokens = request.budget.max_input_tokens
        if request.budget.max_output_tokens:
            budget.max_output_tokens = request.budget.max_output_tokens
        if request.budget.max_estimated_cost:
            budget.max_estimated_cost = request.budget.max_estimated_cost

    tracker = ObservabilityTracker()
    logger.info(
        "🚀 Pipeline execution started: %d raw items [Caller=%s, GoogleAuth=%s, BYOK=%s]",
        len(request.feedback_items),
        identifier,
        is_google,
        has_custom_key,
    )

    # ── Step 1: Local Cleaning & Deduplication ────────────────────────────────
    cleaning_result = clean_feedback(
        request.feedback_items,
        near_duplicate_threshold=settings.near_duplicate_threshold,
        max_clusters=settings.max_clean_clusters,
    )
    logger.info(
        "🧹 [Stage 1/8: Cleaner] Raw items: %d -> Clean clusters: %d (Noise/Spam removed: %d)",
        len(request.feedback_items),
        len(cleaning_result.clusters),
        cleaning_result.summary.noise_items,
    )

    if len(cleaning_result.clusters) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fewer than 2 distinct feedback items remain after local cleaning. Please provide more diverse items.",
        )

    # ── Step 2: Rubric Generation & Caching ──────────────────────────────────
    rubric, is_fallback_rubric = await generate_rubric(
        request.product_context,
        budget=budget,
        tracker=tracker,
        api_key=active_api_key,
    )
    logger.info(
        "📐 [Stage 2/8: Rubric] Active criteria: %d dimensions (%s) [Fallback: %s]",
        len(rubric.dimensions),
        ", ".join(d.name for d in rubric.dimensions),
        is_fallback_rubric,
    )

    # ── Step 3: Local Pre-Ranking & Candidate Selection ──────────────────────
    max_cand = min(request.max_candidates, settings.max_tournament_items)
    tournament_clusters, lower_clusters, pre_rank_scores = pre_rank_clusters(
        cleaning_result.clusters,
        request.product_context,
        max_candidates=max_cand,
    )
    logger.info(
        "📊 [Stage 3/8: Pre-Ranking] Contenders selected: %d for Swiss tournament (Lower-priority: %d)",
        len(tournament_clusters),
        len(lower_clusters),
    )

    # ── Step 4: Tournament State Initialization ──────────────────────────────
    candidates = init_candidates(tournament_clusters, pre_rank_scores)
    max_rounds = compute_num_rounds(len(candidates))

    # ── Step 5: Swiss Tournament Execution ───────────────────────────────────
    all_matches = []
    global_pair_id = 1
    early_stopped = False
    early_stop_reason = ""
    previous_top_ids: list[str] = []
    rounds_completed = 0

    logger.info("⚔️ [Stage 4/8: Tournament] Commencing Swiss pairing (%d rounds planned, %d candidates)", max_rounds, len(candidates))

    for round_num in range(1, max_rounds + 1):
        rounds_completed = round_num

        # Check early stopping before generating pairs
        stopped, reason = check_early_stopping(
            round_num, max_rounds, candidates, previous_top_ids, budget
        )
        if stopped:
            early_stopped = True
            early_stop_reason = reason
            logger.info("⏱️ [Stage 4/8: Tournament] Early stopping triggered at round %d: %s", round_num, reason)
            break

        pairings = generate_pairings(candidates, round_num)
        if not pairings:
            break

        pair_specs = []
        for id_a, id_b in pairings:
            pair_specs.append((id_a, id_b, global_pair_id))
            global_pair_id += 1

        matches = await judge_pairs(
            pair_specs=pair_specs,
            candidates=candidates,
            rubric=rubric,
            product_context=request.product_context,
            round_num=round_num,
            budget=budget,
            tracker=tracker,
            api_key=active_api_key,
        )

        for match in matches:
            apply_match_result(candidates, match)
            all_matches.append(match)

        logger.info("⚔️ [Stage 4/8: Tournament] Round %d/%d completed: %d matches recorded", round_num, max_rounds, len(matches))

        # Track top candidates for stability convergence check
        previous_top_ids = [c.id for c in rank_candidates(candidates)[:3]]

    # ── Step 6: Final Ranking & Tier Assignment ──────────────────────────────
    ranked = rank_candidates(candidates)
    ranked = assign_tiers(ranked)

    # ── Step 7: Build Evidence & Explanations ────────────────────────────────
    cand_text_map = {c.id: c.text for c in candidates}
    ranked_items: list[RankedItem] = []

    for i, c in enumerate(ranked):
        reasons = [m.reason for m in c.history if m.winner_id == c.id]
        source_labels = list(set(m.source for m in c.history))

        beaten = [
            cand_text_map.get(m.item_b_id if m.item_a_id == c.id else m.item_a_id, "competitor")
            for m in c.history
            if m.winner_id == c.id
        ]
        lost_to = [
            cand_text_map.get(m.item_b_id if m.item_a_id == c.id else m.item_a_id, "competitor")
            for m in c.history
            if m.winner_id != c.id
        ]

        ranked_items.append(
            RankedItem(
                rank=i + 1,
                id=c.id,
                text=c.text,
                merged_feedback=c.merged_feedback,
                report_count=c.report_count,
                severity=c.severity,
                elo=c.elo,
                wins=c.wins,
                losses=c.losses,
                tier=c.tier,
                reasons=reasons,
                source_labels=source_labels if source_labels else ["Local rule (obvious pair)"],
                beaten_items=beaten,
                lost_to_items=lost_to,
            )
        )

    lower_priority = [
        LowerPriorityItem(
            id=cluster.id,
            text=cluster.representative_text,
            local_pre_rank_score=pre_rank_scores.get(cluster.id, 0.0),
            report_count=cluster.report_count,
            severity=cluster.severity,
            merged_feedback=cluster.merged_feedback,
        )
        for cluster in lower_clusters
    ]

    tier_counts = {
        "Now": sum(1 for item in ranked_items if item.tier == "Now"),
        "Next": sum(1 for item in ranked_items if item.tier == "Next"),
        "Later": len(lower_priority) + sum(1 for item in ranked_items if item.tier == "Later"),
    }
    logger.info("🏆 [Stage 5/8: Elo & Tiers] Ratings finalized: Now: %d, Next: %d, Later: %d", tier_counts["Now"], tier_counts["Next"], tier_counts["Later"])

    # ── Step 8: Build Telemetry & Response ───────────────────────────────────
    summary = PipelineSummary(
        raw_items=len(request.feedback_items),
        unique_clusters=cleaning_result.summary.unique_clusters,
        clean_items=cleaning_result.summary.clean_items,
        tournament_candidates=len(candidates),
        rounds=rounds_completed,
        pairwise_comparisons=len(all_matches),
        llm_requests=budget.used_llm_requests,
        cache_hits=tracker.cache_hits,
        local_decisions=tracker.local_decisions,
        fallback_decisions=tracker.fallback_decisions,
        early_stopped=early_stopped,
        early_stop_reason=early_stop_reason,
        input_tokens=budget.used_input_tokens,
        output_tokens=budget.used_output_tokens,
        estimated_cost=budget.estimated_cost,
    )

    job_id = f"job_{uuid4().hex[:12]}"

    # Persist usage and job receipt to DigitalOcean PostgreSQL
    await record_user_usage_in_db(
        identifier=identifier,
        is_google=is_google,
        is_byok=has_custom_key,
    )
    await save_ranking_job(
        job_id=job_id,
        user_email=user_info.get("email") if user_info else None,
        user_ip=client_ip,
        product_context=request.product_context,
        raw_items_count=len(request.feedback_items),
        clean_items_count=cleaning_result.summary.clean_items,
        ranked_items_count=len(ranked_items),
        summary_dict=summary.model_dump(),
        rubric_dict=rubric.model_dump(),
        ranked_items_list=[item.model_dump() for item in ranked_items],
        lower_priority_list=[item.model_dump() for item in lower_priority],
        matches_list=[m.model_dump() for m in all_matches],
        cost_estimate=budget.estimated_cost,
        is_byok=has_custom_key,
    )

    logger.info(
        "💾 [Stage 6/8: Persistence] Job %s saved to DB | Tokens: %d In / %d Out | Cost: $%.5f",
        job_id,
        budget.used_input_tokens,
        budget.used_output_tokens,
        budget.estimated_cost,
    )

    return RankResponse(
        job_id=job_id,
        rubric=rubric,
        cleaning_summary=cleaning_result.summary,
        summary=summary,
        ranked_items=ranked_items,
        lower_priority_candidates=lower_priority,
        matches=all_matches,
        warnings=budget.warnings,
    )


# ── History & Backlog Persistence Endpoints ─────────────────────────────────

@app.get(
    "/history",
    tags=["Feedback Prioritization"],
    summary="List Recent Ranking Runs",
    response_description="Recent prioritized backlog runs stored in DigitalOcean PostgreSQL",
)
async def list_history(limit: int = 15, google_id_token: str = ""):
    """Fetch history of backlog prioritization jobs from PostgreSQL."""
    user_info = await verify_google_id_token(google_id_token) if google_id_token else None
    user_email = user_info.get("email") if user_info else None
    jobs = await get_recent_jobs(limit=min(limit, 50), user_email=user_email)
    return {"jobs": jobs}


@app.get(
    "/history/{job_id}",
    tags=["Feedback Prioritization"],
    summary="Fetch Historical Ranking Backlog",
    response_description="Complete snapshot of a historical prioritization job",
)
async def get_history_job(job_id: str):
    """Retrieve full ranking run receipt by job ID from PostgreSQL."""
    job = await get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found in database")
    return job
