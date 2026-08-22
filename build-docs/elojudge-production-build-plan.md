# EloJudge Production-Aware Build Plan

> **Goal:** Build a reliable, explainable feedback-prioritization engine that minimizes LLM usage and remains useful when models, networks, or budgets fail.

## Product definition

### Name

**EloJudge** — an explainable feedback-prioritization engine.

### One-line pitch

> “EloJudge turns messy user feedback into a prioritized, explainable backlog. It cleans and clusters feedback locally, compares only uncertain high-value candidates, and produces a ranked roadmap with evidence.”

### Problem

Product teams receive large volumes of feedback through support tickets, surveys, app reviews, chats, and issue trackers. Prioritizing these requests using intuition, spreadsheets, or the loudest customer can be inconsistent and difficult to defend.

### Solution

EloJudge will:

1. Enforce request and cost limits before processing.
2. Clean, normalize, and deduplicate feedback locally.
3. Cluster similar feedback and aggregate frequency and severity.
4. Generate or retrieve a cached product-specific rubric.
5. Pre-rank candidates locally.
6. Resolve obvious comparisons using deterministic rules.
7. Send only uncertain comparisons to an inexpensive model first.
8. Escalate difficult or high-impact comparisons to a stronger model.
9. Run a small Swiss-style tournament with Elo updates.
10. Cache valid judgments and stop early when the ranking is stable.
11. Return a prioritized backlog with an evidence and cost trail.

### Honest innovation framing

Pairwise comparison, Swiss tournaments, and Elo aggregation are established techniques. The innovation is combining them with local preprocessing, feedback clustering, model routing, caching, cost controls, and explainable evidence for product-feedback triage.

Use this wording:

> “I apply a proven pairwise-ranking method to product-feedback triage, while using local preprocessing, selective model calls, and evidence trails to make the workflow explainable and cost-efficient.”

## Product principles

- AI is used only where judgment is genuinely needed.
- Deterministic work runs locally whenever possible.
- Every result identifies whether it came from an AI model, a local rule, a cache, or a demo fallback.
- The system must remain useful when the LLM is unavailable.
- Cost, latency, quality, and cache behavior are observable.
- Uncompared items are never presented as fully ranked.
- High-impact issues such as security, data loss, and outages require stricter review.

## Scope

### MVP

- Product-context input.
- Feedback input, one item per line.
- Input validation and hard limits.
- Local rule-based cleaning.
- Exact deduplication.
- Lightweight near-duplicate merging.
- Local pre-ranking.
- One cached or fallback rubric.
- Top-eight candidate limit.
- Swiss tournament with Elo updates.
- Two comparisons per LLM request initially.
- Strict JSON validation and one retry.
- Local fallback for failed judgments.
- Cleaning statistics and source labels.
- Explainable match history.
- Cost and request metrics.
- Demo dataset and offline fallback.

### Production-oriented additions

Add after the MVP works:

- Feedback clustering and aggregation.
- Frequency, severity, affected-user, and recency signals.
- Exact rubric and pairwise-result caches.
- Small-model-first routing.
- Confidence-based escalation.
- Local resolution for obvious comparisons.
- Per-user, per-job, and global budgets.
- Token and cost observability.
- Semantic caching only after evaluation.
- Active pair selection.
- Early stopping when ranking is stable.
- Background processing for large jobs.
- PostgreSQL persistence and Redis caching.
- Human review for ambiguous or high-impact decisions.

### Exclude from the first production iteration

- Full round-robin comparison for large datasets.
- Complex ML training.
- Unvalidated semantic caching.
- Unbounded autonomous retries.
- Long LLM-generated reports.
- Authentication before the core workflow is reliable.
- Team collaboration before persistence and authorization are designed properly.
- Advanced confidence intervals or Bradley–Terry fitting unless evaluation justifies them.

## Architecture

```text
Browser or ingestion API
   |
   v
API gateway
   +--> Authentication and rate limits
   +--> Per-user and per-job budget checks
   |
   v
Ranking service
   +--> Validate and normalize input
   +--> Local cleaner
   +--> Exact deduplication
   +--> Near-duplicate clustering
   +--> Frequency/severity aggregation
   +--> Local pre-ranking
   |
   v
Cache layer
   +--> Rubric cache
   +--> Exact pairwise-result cache
   +--> Optional semantic cache
   |
   v
Decision layer
   +--> Obvious-pair local rules
   +--> Cheap model for normal comparisons
   +--> Strong model for uncertain or high-impact comparisons
   +--> Retry and fallback policy
   |
   v
Tournament engine
   +--> Swiss pairings
   +--> Elo updates
   +--> Early stopping
   +--> Evidence history
   |
   v
Response builder
   +--> Ranked backlog
   +--> Lower-priority items
   +--> Cleaning and cost metrics
   +--> Source labels
```

Only rubric generation and genuinely uncertain judgments should require an external model. Cleaning, normalization, clustering where possible, candidate selection, pairing, Elo calculation, sorting, caching, fallback behavior, and rendering should remain local.

## Input contract

Example request:

```json
{
  "product_context": "QuickNote is a minimalist note-taking app for students. Its goals are fast capture, simple organization, and exam preparation.",
  "feedback_items": [
    "Add dark mode",
    "Export notes to PDF",
    "Better search with filters",
    "Add tags to notes",
    "Sync across devices",
    "Add voice-to-text input",
    "Create folders for organization",
    "Add a daily note template"
  ],
  "max_candidates": 8,
  "mode": "interactive"
}
```

Enforce these limits before any model request:

- Product context: at least 20 characters.
- Raw feedback: maximum 100 in production; 20 for the initial MVP.
- Each item: maximum 300 characters.
- Clean clusters: maximum 30 per job.
- Tournament candidates: maximum 8 for the initial production version.
- LLM requests: configurable per job.
- Input and output tokens: configurable per job.
- Estimated spend: configurable per job.
- Reject or clearly mark anything exceeding the limit; never silently create unlimited work.
- Never expose API keys to the browser.

## Cost-control policy

### Per-job budget

Every ranking job should have a budget object:

```json
{
  "max_llm_requests": 12,
  "max_input_tokens": 50000,
  "max_output_tokens": 5000,
  "max_estimated_cost": 0.10,
  "max_retries": 2
}
```

When a limit is reached:

1. Stop nonessential model calls.
2. Complete the ranking with cached results and local fallbacks.
3. Return a partial-comparison indicator.
4. Report the reason clearly to the user.

### Per-user and global limits

Implement:

- Requests per minute.
- Ranking jobs per day.
- Monthly token allowance.
- Monthly spend cap.
- Separate free and paid-plan quotas.
- Global circuit breaker for unexpected provider usage.

If the global budget is exceeded, route to local mode, serve cached results, or temporarily disable nonessential AI features.

### Cost attribution

Record cost by:

- User or tenant.
- Product.
- Feature.
- Model.
- Environment.
- Request type.
- Cache status.
- Fallback status.

## Cost-efficient pipeline

```text
Raw feedback
   |
   +--> Validate limits
   +--> Remove blank, spammy, and URL-only entries locally
   +--> Exact deduplication
   +--> Lightweight near-duplicate clustering
   +--> Optional semantic clustering for large datasets
   +--> Aggregate frequency, severity, recency, and user segments
   +--> Local pre-ranking
   +--> Resolve obvious pairs locally
   +--> Select uncertain top candidates
   +--> Retrieve or generate cached rubric
   +--> Compare with cheap model
   +--> Escalate only uncertain or high-impact matches
   +--> Cache every valid decision
   +--> Run Swiss tournament
   +--> Stop early if ranking is stable
   +--> Assemble explanations locally
```

## Local cleaning and clustering

The cleaner runs before every model request.

### Filtering

Remove:

- Empty or whitespace-only items.
- Clearly meaningless short entries.
- URL-only items.
- Repeated-character spam.
- Obvious automated noise.

Use conservative rules for all-caps content because an urgent incident may legitimately be written in uppercase.

### Exact deduplication

Normalize by:

- Trimming whitespace.
- Lowercasing.
- Collapsing repeated spaces.
- Normalizing punctuation.

Preserve the original display text and retain duplicate examples for explanation.

### Near-duplicate merging

Use `difflib.SequenceMatcher` with an initial threshold near `0.85` for the MVP. Treat this as a lightweight heuristic, not semantic truth.

For larger datasets, cluster feedback using an embedding model or vector service only after measuring whether its quality improvement justifies its cost. Embeddings can be generated asynchronously and reused across jobs.

### Aggregation

Each cluster should retain:

```json
{
  "id": "cluster_1",
  "representative_text": "App crashes on login",
  "merged_feedback": ["Login screen keeps crashing"],
  "report_count": 17,
  "severity": "high",
  "affected_segments": ["new users", "mobile users"],
  "last_seen_at": "2026-08-22T08:00:00Z"
}
```

Frequency and severity provide valuable local signals and help the model make better decisions with less context.

## Rubric generation and caching

Generate a rubric once per product context and cache it.

Example:

```json
{
  "dimensions": [
    {
      "name": "Core-goal impact",
      "weight": 0.40,
      "description": "How strongly the request advances stated product goals"
    },
    {
      "name": "User value and frequency",
      "weight": 0.25,
      "description": "Expected breadth, frequency, and urgency of benefit"
    },
    {
      "name": "Delivery feasibility",
      "weight": 0.20,
      "description": "Higher score means easier or lower-risk delivery"
    },
    {
      "name": "Product fit",
      "weight": 0.15,
      "description": "Consistency with product positioning and constraints"
    }
  ]
}
```

Validate:

- Exactly 3–5 dimensions.
- Required name, weight, and description fields.
- Numeric, non-negative weights.
- Weights normalized to sum to 1.0.
- Maximum rubric length.
- Fallback rubric if generation fails.

Cache key:

```text
hash(tenant_id + product_context + rubric_prompt_version)
```

Invalidate the rubric when product goals, rubric version, or important configuration changes.

## Local pre-ranking

Use deterministic signals such as:

- Product-goal keyword overlap.
- Report frequency.
- Severity.
- Recency.
- Affected-user breadth.
- Impact terms such as `crash`, `security`, `sync`, `search`, and `data loss`.
- Urgency terms such as `blocked`, `cannot`, `broken`, and `urgent`.
- Feasibility only if a reliable local signal exists.

The local score is for candidate selection and fallback, not a claim of objective product value.

Example:

```python
local_score = (
    3 * goal_overlap
    + 3 * severity_score
    + 2 * normalized_frequency
    + 2 * affected_segment_count
    + 1 * recency_score
)
```

## Obvious-pair handling

Before calling a model, test whether the result is clear enough for a deterministic decision.

Examples that may be locally resolvable:

- A confirmed data-loss issue versus a cosmetic animation.
- A security vulnerability versus a minor theme preference.
- A complete login outage versus a low-impact enhancement.

Use a confidence margin:

```python
if abs(score_a - score_b) >= LOCAL_DECISION_MARGIN:
    decision = local_winner
    source = "local_rule"
else:
    send_to_model(pair)
```

Do not use local rules for close or strategically important comparisons. Label every local decision honestly.

## Model routing

Use a model hierarchy:

| Situation | Action |
|---|---|
| Exact cached result | Return cache result |
| High-confidence local decision | Use local rule |
| Normal uncertain comparison | Use inexpensive model |
| Cheap model has low confidence | Escalate to stronger model |
| Security, data loss, outage, or compliance issue | Use stronger model or human review |
| Provider failure or budget exhaustion | Use fallback |

If the provider supplies confidence, use it carefully. Otherwise estimate confidence using agreement between local signals, repeated cheap-model judgments, or an evaluation-trained classifier.

Do not route to a cheaper model solely because it is cheaper. Validate winner agreement and ranking quality on a labeled test set first.

## Pairwise judgment API

Send only the information needed for the current comparison:

```json
{
  "pair_id": "pair_123",
  "rubric": [
    {"name": "Core-goal impact", "weight": 0.4},
    {"name": "User value", "weight": 0.25},
    {"name": "Feasibility", "weight": 0.2},
    {"name": "Product fit", "weight": 0.15}
  ],
  "item_a": "Better search with filters",
  "item_b": "Add dark mode",
  "metadata": {
    "a_report_count": 12,
    "b_report_count": 4,
    "a_severity": "medium",
    "b_severity": "low"
  }
}
```

Expected response:

```json
{
  "pair_id": "pair_123",
  "winner": "A",
  "reason": "Search filters better support the product's study and organization goals.",
  "confidence": 0.86
}
```

Requirements:

- JSON only.
- One concise reason.
- Maximum reason length, such as 40 words.
- Strict pair ID validation.
- Winner must be `A` or `B`.
- No hidden chain-of-thought request.
- Preserve visible-label-to-item-ID mapping.
- Alternate A/B presentation order.

## Caching strategy

### Exact cache

Cache rubric results and pairwise judgments.

A pairwise cache key should include:

```text
tenant_id
product_context_hash
rubric_hash
unordered_item_pair
prompt_version
model_version
```

The pair key must be order-independent so `A vs B` and `B vs A` can reuse the same judgment, while the UI still maps labels correctly.

### Semantic cache

Add only after evaluation. Use it conservatively:

- Exact match: automatic reuse.
- High-confidence semantic match under the same product and rubric: possible reuse.
- Medium-confidence match: call the model.
- Low-confidence match: do not reuse.

Never reuse a semantic result across different products, tenants, rubric versions, or materially different feedback clusters.

### Cache invalidation

Invalidate results when:

- Product context changes materially.
- Rubric version changes.
- Prompt behavior changes.
- Model version changes significantly.
- Feedback aggregation metadata changes enough to alter the judgment.

## Prompt and token optimization

- Keep stable instructions at the beginning of the prompt.
- Send only the current pair and compact metadata.
- Do not send the full feedback dataset repeatedly.
- Avoid long few-shot examples.
- Use structured compact rubric representations.
- Limit output tokens.
- Request one-sentence reasons.
- Do not request chain-of-thought.
- Use provider prompt caching where available.
- Measure token usage before and after every prompt change.

## Swiss tournament

### Candidate count

- Eight or fewer clean candidates: tournament all.
- More than eight: select top eight using local pre-ranking and cluster-level signals.
- Remaining clusters go to `lower_priority_candidates`.

### Pairings

- Round 1: top half versus bottom half by local pre-rank.
- Later rounds: similar win records first, then Elo and local pre-rank.
- Never schedule a rematch.
- Give one bye for an odd number of candidates.
- Track every pairing.

### Early stopping

Use a minimum of two rounds and a maximum of four rounds initially. Stop only when:

- The top- ranking has remained stable for two rounds.
- The Elo margin is sufficiently large.
- Remaining matches cannot realistically change the requested top- ordering.
- The job is approaching its budget limit.

When stopping early, return `early_stopped: true` and explain why.

## Elo updates

Initialize every candidate at 1200.

```python
K = 24
expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
expected_b = 1 - expected_a
score_a = 1 if a_wins else 0
score_b = 1 - score_a
rating_a = rating_a + K * (score_a - expected_a)
rating_b = rating_b + K * (score_b - expected_b)
```

Store:

- Round.
- Pair ID.
- Item IDs.
- Winner.
- Reason.
- Source.
- Model.
- Cache hit status.
- Ratings before and after.
- Confidence, when available.

## Ranking response

```json
{
  "rubric": {"dimensions": []},
  "cleaning_summary": {
    "raw_items": 14,
    "removed_empty_or_short": 1,
    "removed_spam": 1,
    "removed_exact_duplicates": 2,
    "merged_near_duplicates": 2,
    "clean_items": 8
  },
  "summary": {
    "unique_clusters": 11,
    "tournament_candidates": 8,
    "rounds": 3,
    "pairwise_comparisons": 12,
    "llm_requests": 4,
    "cache_hits": 5,
    "local_decisions": 2,
    "fallback_decisions": 0,
    "early_stopped": true,
    "input_tokens": 3200,
    "output_tokens": 520,
    "estimated_cost": 0.012
  },
  "ranked_items": [],
  "lower_priority_candidates": [],
  "matches": [],
  "warnings": []
}
```

## Explanation design

Assemble explanations locally from stored evidence rather than making an additional summary call.

Each ranked item should show:

- Final Elo.
- Wins and losses.
- Report count.
- Severity.
- Main rubric dimensions.
- Features it beat.
- Features it lost to.
- One-sentence reasons.
- Source labels.
- Whether the result was cached.

Example:

```text
Search ranked #1 because it beat dark mode and daily templates in direct comparisons. The strongest reason was its impact on the product's core study workflow.
```

If an item was not fully compared, display:

> Lower-priority candidate — not fully compared.

## Reliability and fallback

Fallback order:

1. Exact cached result.
2. Valid previous result for the same product and pair.
3. Local deterministic winner.
4. Default rubric.
5. Prepared demo result for the demo dataset.

Retry policy:

- Retry malformed JSON once with a shorter prompt.
- Do not retry indefinitely.
- Use exponential backoff for transient provider errors.
- Do not retry permanent validation or authorization errors.
- Count retries against the job budget.

Label results:

- `AI judgment`.
- `Cached AI judgment`.
- `Local fallback`.
- `Demo dataset result`.
- `Human-reviewed decision`.

## Observability

Capture a request-level record:

```json
{
  "request_id": "req_123",
  "tenant_id": "tenant_42",
  "feature": "pairwise_judgment",
  "model": "cheap-model",
  "input_tokens": 820,
  "output_tokens": 74,
  "latency_ms": 940,
  "cache_hit": false,
  "fallback": false,
  "estimated_cost": 0.0008
}
```

Monitor:

- Cost per ranking job.
- Cost per tenant and product.
- Input and output tokens.
- Cache hit rate.
- Local-decision rate.
- Model-routing distribution.
- Retry and failure rate.
- Fallback rate.
- Average comparisons per job.
- Ranking stability.
- Human agreement.
- Latency.

Create alerts for:

- Unusual daily spend.
- Sudden token growth.
- Cache hit-rate collapse.
- Provider error spikes.
- Unexpected model routing to the expensive model.
- High fallback rates.

## Quality evaluation

Create a labeled evaluation dataset containing:

- Product context.
- Two feedback items.
- Human-selected winner.
- Acceptable reason.
- Severity and ambiguity labels.

Compare:

- Local rules.
- Cheap model.
- Strong model.
- Cached or semantic-cache decisions.

Measure:

- Pairwise winner accuracy.
- Top-three agreement.
- Ranking correlation.
- Stability across repeated runs.
- High-impact issue recall.
- False prioritization of cosmetic features.
- Cost per accepted decision.

Only enable cheaper routing or semantic caching when quality remains within an agreed threshold.

## Tech stack

### MVP

- Python 3.11+.
- FastAPI.
- Uvicorn.
- Pydantic.
- `re`, `unicodedata`, and `difflib`.
- A low-cost Gemini Flash-class model or equivalent.
- Plain HTML, CSS, and JavaScript.
- In-memory dictionaries.
- Pytest.

### Production

- PostgreSQL for durable products, clusters, matches, and ranking history.
- Redis for rubric, pairwise, rate-limit, and optional semantic caches.
- Background workers for batch and asynchronous processing.
- Model gateway for routing, token tracking, and provider failover.
- OpenTelemetry-compatible traces and metrics.
- Object storage for exported reports if needed.

## Suggested structure

```text
elojudge/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── schemas.py
│   ├── cleaner.py
│   ├── clustering.py
│   ├── aggregation.py
│   ├── rubric.py
│   ├── preprocess.py
│   ├── router.py
│   ├── cache.py
│   ├── budget.py
│   ├── tournament.py
│   ├── judge.py
│   ├── fallback.py
│   ├── observability.py
│   └── demo_data.py
├── static/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── tests/
│   ├── test_cleaner.py
│   ├── test_clustering.py
│   ├── test_budget.py
│   ├── test_router.py
│   ├── test_tournament.py
│   ├── test_elo.py
│   └── test_judge_parser.py
├── .env.example
├── requirements.txt
└── README.md
```

## Environment variables

```bash
LLM_API_KEY=
LLM_MODEL_CHEAP=cheap-model
LLM_MODEL_STRONG=strong-model
MAX_RAW_ITEMS=100
MAX_CLEAN_CLUSTERS=30
MAX_TOURNAMENT_ITEMS=8
PAIRS_PER_LLM_REQUEST=2
MAX_LLM_REQUESTS_PER_JOB=12
MAX_INPUT_TOKENS_PER_JOB=50000
MAX_OUTPUT_TOKENS_PER_JOB=5000
MAX_ESTIMATED_COST_PER_JOB=0.10
NEAR_DUPLICATE_THRESHOLD=0.85
LLM_TIMEOUT_SECONDS=20
CACHE_TTL_SECONDS=86400
ENABLE_SEMANTIC_CACHE=false
ENABLE_EARLY_STOPPING=true
```

Security:

- Put `.env` in `.gitignore`.
- Commit only `.env.example`.
- Keep all provider calls on the backend.
- Never log secrets.
- Redact sensitive feedback from logs.
- Apply tenant isolation to caches.
- Encrypt persistent feedback and ranking history where required.

## Frontend flow

### Input

- Product context textarea.
- Feedback textarea or ingestion option.
- Demo-data button.
- Mode selector: interactive or background.
- Notice explaining limits and cost-efficient processing.

### Processing

```text
1/8 Validating request and checking budget
2/8 Cleaning feedback locally
3/8 Clustering and aggregating similar reports
4/8 Loading or generating product rubric
5/8 Selecting candidates and resolving obvious pairs
6/8 Running Swiss comparison round 2 of 4
7/8 Updating Elo ratings and checking stability
8/8 Building explainable roadmap
```

### Results

Show:

- `Now`, `Next`, and `Later` sections.
- Submitted, cleaned, and clustered item counts.
- Comparisons and model requests.
- Cache hits and local decisions.
- Estimated cost.
- Ranking confidence or stability indicator.
- Match reasons.
- Rubric.
- Lower-priority candidates.
- Warnings for partial, early-stopped, or fallback results.

## API budget example

For eight candidates and four Swiss rounds:

```text
16 pairwise matches
÷ 2 pairs per request
= 8 comparison requests
```

With one rubric request:

```text
1 rubric request + 8 comparison requests = 9 requests
```

In production, the target should be lower when caching, local decisions, early stopping, and model routing are effective. The system must measure actual usage rather than assuming every job uses the maximum.

## Demo dataset

Product context:

```text
QuickNote is a minimalist note-taking app for students. Its goals are to help users capture ideas quickly, reduce friction in organizing notes, and support exam preparation workflows.
```

Feedback:

```text
Add dark mode
Export notes to PDF
Better search with filters
Add tags to notes
Sync across devices
Add voice-to-text input
Create folders for organization
Add a daily note template
```

Use the live system to determine the ranking. Keep a precomputed result only for network or provider failure. Do not hardcode a live ranking as if it were the current AI decision.

## Implementation plan

### Before the event

- Create repository and virtual environment.
- Add `.env.example` and secret checks.
- Implement and test the local cleaner.
- Implement exact deduplication and near-duplicate merging.
- Implement local pre-ranking.
- Implement Swiss pairing and Elo updates.
- Implement budget tracking and request accounting.
- Implement a mock model client.
- Test rubric parsing and pairwise parsing.
- Prepare demo data and precomputed fallback.
- Install dependencies and rehearse online/offline demos.

### First 30 minutes

- Start FastAPI.
- Serve input page.
- Implement `POST /rank` with mocked ranking.
- Display a hardcoded result.
- Commit `chore: runnable MVP shell`.

### 30–75 minutes

- Implement cleaner and normalization.
- Add exact and near-duplicate merging.
- Add local pre-ranking.
- Add budget object and request counters.
- Implement Swiss pairing and Elo updates.
- Add tests.
- Commit `feat: local preprocessing and tournament engine`.

### 75–120 minutes

- Add rubric generation and caching.
- Add pairwise cache interface.
- Add two-pair batching.
- Add strict response validation.
- Add one retry and deterministic fallback.
- Add source labels.
- Commit `feat: cached and resilient judge`.

### 120–165 minutes

- Add model routing abstraction.
- Add local obvious-pair handling.
- Connect results to the UI.
- Display cleaning, model, cache, and cost metrics.
- Show reasons and match history.
- Commit `feat: explainable cost-aware ranking`.

### 165–210 minutes

- Add demo-data loading.
- Test malformed responses and provider outage.
- Test budget exhaustion.
- Verify API key protection.
- Rehearse the 90-second pitch.
- Commit and push final code.

### After the MVP

- Add cluster-level aggregation.
- Add cheap-model/strong-model routing.
- Add evaluation set and quality gates.
- Add Redis and PostgreSQL.
- Add background jobs.
- Add semantic cache only after validation.
- Add early stopping and active pair selection.
- Add human-review workflow for high-impact decisions.

### Final buffer

- Do not add major features in the final 30 minutes.
- Fix only demo-affecting issues.
- Keep local fallback ready.
- Keep a phone hotspot available if permitted.

## Testing checklist

### Cleaner and clustering

- Empty and whitespace-only items are removed.
- Short but meaningful requests are preserved.
- URL-only entries are removed.
- Repeated-character noise is removed.
- All-caps urgent feedback is not blindly removed.
- Case-insensitive exact duplicates merge.
- Near-duplicates merge above the configured threshold.
- Original text and merged examples are preserved.
- Cluster counts and frequencies are correct.

### Budget and reliability

- Raw-item limits are enforced.
- Token limits are enforced.
- Cost limits are enforced.
- Retry limits are enforced.
- Permanent errors are not retried indefinitely.
- Tenant cache isolation works.
- Global circuit breaker activates.
- API keys never appear in logs or frontend code.

### Model routing and cache

- Exact rubric cache works.
- Exact pairwise cache is order-independent.
- Cache keys include product, rubric, prompt, and model versions.
- Local obvious-pair handling works.
- Cheap-model escalation works.
- High-impact issues use stricter routing.
- Semantic cache is disabled by default until evaluated.

### Tournament and Elo

- Eight candidates produce four matches per round.
- No pair occurs twice.
- Odd candidate counts receive correct byes.
- Winners gain Elo.
- Losers lose Elo.
- Underdog wins produce larger gains.
- Early stopping reports its reason.
- Final sorting is deterministic.

### LLM integration

- Valid rubric JSON parses.
- Invalid rubric uses the default rubric.
- Valid batched judgments map correctly.
- Missing judgments trigger one retry.
- A second failure uses local fallback.
- Invalid winners are rejected.
- Reasons obey length limits.
- Cached visible A/B mappings are correct.

### Quality evaluation

- Cheap and strong models are compared against human labels.
- Local decisions are measured separately.
- Top-three ranking quality is measured.
- High-impact issue recall is measured.
- Ranking stability is measured across repeated runs.
- Semantic-cache reuse is tested for false matches.

## Judge Q&A

### Why clean locally before using an LLM?

Local cleaning removes noise and duplicates before any model call. It reduces latency and spend while preventing the same complaint from being counted multiple times.

### Why not use embeddings for everything?

Embeddings may improve semantic clustering, but they add infrastructure and cost. Start with deterministic rules and lightweight similarity; add embeddings only when evaluation shows a meaningful benefit.

### Why not ask an LLM to score every item from 1–10?

Independent scores can drift and be difficult to compare. Head-to-head judgments force explicit trade-offs under one rubric, and Elo aggregates those decisions.

### Why use a small model first?

Most comparisons are ordinary and do not need the strongest model. A cheap model can handle normal cases, while difficult, ambiguous, or high-impact cases are escalated.

### How do you prevent cost explosions?

Use local preprocessing, clustering, candidate caps, caching, short prompts, batching, local obvious-pair decisions, early stopping, model routing, token budgets, spend caps, rate limits, and a global circuit breaker.

### What happens if the API fails?

The system uses cached decisions, a predefined rubric, local pre-ranking, deterministic pairwise fallbacks, and a prepared demo result. Every result is labeled honestly.

### Can it scale?

A production version can ingest feedback asynchronously, cluster reports, persist history, process jobs in the background, route across models, and include human review. The initial version intentionally focuses on a reliable, cost-bounded workflow.

## Pitch

> “Product teams receive large amounts of feedback, but they often prioritize it using intuition, spreadsheets, or the loudest request. EloJudge first cleans and clusters that feedback locally, so we do not spend model tokens comparing duplicate complaints. It then uses a product-specific rubric, resolves obvious trade-offs locally, and sends only uncertain high-value comparisons to an inexpensive model. Difficult or high-impact decisions can be escalated to a stronger model. A Swiss tournament and Elo ratings produce a global ordering, while every decision keeps its reason and source label. Caches, batching, early stopping, token budgets, and deterministic fallbacks keep the workflow reliable and affordable. The established technique is pairwise Elo ranking; the product innovation is applying it as a cost-aware, explainable feedback-triage workflow.”

## Non-negotiables

- Clean and cluster before model calls.
- Enforce hard job, user, and global budgets.
- Never send the full dataset repeatedly.
- Cache rubrics and valid pairwise judgments.
- Use a cheap model before a strong model where quality permits.
- Resolve only genuinely obvious pairs locally.
- Keep the tournament capped initially.
- Batch comparisons carefully.
- Validate every structured response.
- Retry only within a strict limit.
- Provide deterministic fallback behavior.
- Show source, cost, cache, and comparison statistics.
- Keep high-impact issues on a stricter review path.
- Never expose secrets.
- Keep innovation claims honest.
- Measure quality before enabling aggressive optimization.
