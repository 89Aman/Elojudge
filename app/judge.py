"""Pairwise LLM judge with batching, order-independent caching, router, and budget tracking."""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from google import genai

from app.budget import JobBudget
from app.cache import cache_layer
from app.config import settings
from app.observability import ObservabilityTracker, estimate_tokens
from app.router import check_obvious_pair, select_model_for_pair
from app.schemas import (
    CandidateState,
    JudgmentBatch,
    MatchRecord,
    Rubric,
    SingleJudgment,
)
from app.utils import extract_json

logger = logging.getLogger(__name__)


# ── Prompt Builder ───────────────────────────────────────────────────────────

def build_comparison_prompt(
    pairs: list[tuple[CandidateState, CandidateState, int, bool]],
    rubric: Rubric,
    product_context: str,
) -> str:
    """Build compact comparison prompt with A/B order alternation."""
    rubric_lines = [f"- {d.name} (wt {d.weight:.2f}): {d.description}" for d in rubric.dimensions]
    rubric_summary = "\n".join(rubric_lines)

    pair_blocks = []
    for cand_a, cand_b, pair_id, swap in pairs:
        vis_a, vis_b = (cand_b, cand_a) if swap else (cand_a, cand_b)
        pair_blocks.append(
            f"Pair {pair_id}:\n"
            f"  A: \"{vis_a.text}\" (Reports: {vis_a.report_count}, Sev: {vis_a.severity})\n"
            f"  B: \"{vis_b.text}\" (Reports: {vis_b.report_count}, Sev: {vis_b.severity})"
        )

    pairs_text = "\n\n".join(pair_blocks)

    return f"""Compare feature requests for: {product_context[:200]}

Rubric:
{rubric_summary}

{pairs_text}

For each pair, pick the winner (A or B) based on rubric and severity. Return ONLY valid JSON:
{{"judgments": [{{"pair_id": 1, "winner": "A", "reason": "Max 15 words rationale.", "confidence": 0.9}}]}}

Rules:
- Exactly {len(pairs)} judgment(s).
- Winner must be "A" or "B".
- Reason max 15 words."""


# ── Parser ───────────────────────────────────────────────────────────────────

def parse_judgment_response(
    raw_text: str,
    expected_count: int,
    expected_pair_ids: list[int],
) -> Optional[list[SingleJudgment]]:
    """Parse and strictly validate LLM judgment JSON."""
    try:
        json_str = extract_json(raw_text)
        data = json.loads(json_str)
        batch = JudgmentBatch(**data)

        if len(batch.judgments) != expected_count:
            return None

        got_ids = {j.pair_id for j in batch.judgments}
        if got_ids != set(expected_pair_ids):
            return None

        for j in batch.judgments:
            if j.winner not in ("A", "B"):
                return None

        return batch.judgments

    except Exception as e:
        logger.warning("Judgment parse error: %s", e)
        return None


# ── LLM Execution Helper ─────────────────────────────────────────────────────

async def call_llm(
    prompt: str,
    model: str,
    api_key: Optional[str] = None,
) -> tuple[Optional[str], int, int, float]:
    """Execute LLM call via Gemini client.

    Returns:
        (raw_text, input_tokens, output_tokens, latency_ms)
    """
    active_key = api_key or settings.api_key
    if not active_key:
        return None, 0, 0, 0.0

    t0 = time.time()
    input_tokens = estimate_tokens(prompt)

    try:
        client = genai.Client(api_key=active_key)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=1024,
                response_mime_type="application/json",
            ),
        )

        latency_ms = (time.time() - t0) * 1000.0
        raw_text = response.text.strip()
        output_tokens = estimate_tokens(raw_text)
        return raw_text, input_tokens, output_tokens, latency_ms

    except Exception as e:
        latency_ms = (time.time() - t0) * 1000.0
        logger.warning("LLM call failed (%s)", e)
        return None, input_tokens, 0, latency_ms


# ── Batch Judging Pipeline ───────────────────────────────────────────────────

async def judge_pairs(
    pair_specs: list[tuple[str, str, int]],
    candidates: list[CandidateState],
    rubric: Rubric,
    product_context: str,
    round_num: int,
    budget: JobBudget,
    tracker: Optional[ObservabilityTracker] = None,
    api_key: Optional[str] = None,
) -> list[MatchRecord]:
    """Evaluate pairwise matches using cache, obvious-pair rules, LLM, or fallback.

    Args:
        pair_specs: list of (id_a, id_b, pair_id)
        candidates: all candidate states
        rubric: product rubric
        product_context: raw product description
        round_num: tournament round number
        budget: job budget tracker
        tracker: telemetry tracker
        api_key: optional custom Gemini API key

    Returns:
        List of MatchRecords ready to apply.
    """
    cand_map = {c.id: c for c in candidates}
    all_matches: list[MatchRecord] = []
    pending_for_llm: list[tuple[str, str, int]] = []

    # 1. Resolve cached pairs & obvious pairs locally
    for id_a, id_b, pair_id in pair_specs:
        cand_a = cand_map[id_a]
        cand_b = cand_map[id_b]

        # 1a. Check Exact Pairwise Cache
        cached_result = cache_layer.get_pair_judgment(
            product_context, rubric, cand_a.text, cand_b.text
        )
        if cached_result:
            winner_text, reason, conf = cached_result
            winner_id = cand_a.id if winner_text == cand_a.text else cand_b.id
            match = MatchRecord(
                round=round_num,
                pair_id=pair_id,
                item_a_id=id_a,
                item_b_id=id_b,
                winner_id=winner_id,
                reason=reason,
                source="Cached AI judgment",
                model="cache",
                confidence=conf,
                cache_hit=True,
            )
            all_matches.append(match)
            if tracker:
                tracker.record_request("judge_pair", "cache", 0, 0, 0.0, cache_hit=True)
            continue

        # 1b. Check Local Obvious Pair Rules
        is_obvious, winner_id, obvious_reason = check_obvious_pair(cand_a, cand_b)
        if is_obvious and winner_id and obvious_reason:
            match = MatchRecord(
                round=round_num,
                pair_id=pair_id,
                item_a_id=id_a,
                item_b_id=id_b,
                winner_id=winner_id,
                reason=obvious_reason,
                source="Local rule (obvious pair)",
                model="local_rule",
                confidence=0.95,
            )
            all_matches.append(match)
            if tracker:
                tracker.record_local_decision()
            continue

        pending_for_llm.append((id_a, id_b, pair_id))

    if not pending_for_llm:
        return all_matches

    # 2. Process remaining pairs in batched LLM calls
    batch_size = settings.pairs_per_request
    for i in range(0, len(pending_for_llm), batch_size):
        batch = pending_for_llm[i : i + batch_size]
        expected_ids = [pid for _, _, pid in batch]

        # Check budget availability
        if not budget.can_make_request():
            for id_a, id_b, pair_id in batch:
                c_a, c_b = cand_map[id_a], cand_map[id_b]
                w_id = id_a if c_a.local_pre_rank >= c_b.local_pre_rank else id_b
                match = MatchRecord(
                    round=round_num,
                    pair_id=pair_id,
                    item_a_id=id_a,
                    item_b_id=id_b,
                    winner_id=w_id,
                    reason="Budget ceiling reached; resolved via local pre-ranking.",
                    source="Local fallback",
                    model="fallback",
                )
                all_matches.append(match)
                if tracker:
                    tracker.record_request("judge_pair", "fallback", 0, 0, 0.0, fallback=True)
            continue

        # Select model and construct prompt with A/B alternation
        cand_pairs_to_prompt = []
        selected_model = settings.model_cheap
        pair_id_map: dict[int, tuple[str, str, bool]] = {}

        for idx, (id_a, id_b, pair_id) in enumerate(batch):
            c_a, c_b = cand_map[id_a], cand_map[id_b]
            model_for_this = select_model_for_pair(c_a, c_b)
            if model_for_this == settings.model_strong:
                selected_model = settings.model_strong

            swap = (pair_id % 2 == 0)
            cand_pairs_to_prompt.append((c_a, c_b, pair_id, swap))
            pair_id_map[pair_id] = (id_a, id_b, swap)

        prompt = build_comparison_prompt(cand_pairs_to_prompt, rubric, product_context)

        # Call LLM (with 1 retry on malformed JSON)
        judgments = None
        for attempt in range(settings.max_retries_per_batch + 1):
            raw_text, in_tok, out_tok, lat_ms = await call_llm(prompt, selected_model, api_key=api_key)
            budget.record_usage(in_tok, out_tok, is_retry=(attempt > 0))
            cost = budget.calculate_cost(in_tok, out_tok)

            if raw_text:
                judgments = parse_judgment_response(raw_text, len(batch), expected_ids)
                if judgments:
                    if tracker:
                        tracker.record_request("judge_batch", selected_model, in_tok, out_tok, lat_ms, cost=cost)
                    break

            if attempt == 0:
                logger.info("Retrying malformed judgment batch...")

        # Process Results or Fallback
        for id_a, id_b, pair_id in batch:
            c_a, c_b = cand_map[id_a], cand_map[id_b]
            swap = pair_id_map[pair_id][2]

            if judgments:
                j = next((j for j in judgments if j.pair_id == pair_id), None)
                if j:
                    if swap:
                        actual_winner_id = id_b if j.winner == "A" else id_a
                    else:
                        actual_winner_id = id_a if j.winner == "A" else id_b

                    winner_cand = cand_map[actual_winner_id]
                    match = MatchRecord(
                        round=round_num,
                        pair_id=pair_id,
                        item_a_id=id_a,
                        item_b_id=id_b,
                        winner_id=actual_winner_id,
                        reason=j.reason,
                        source="AI judgment",
                        model=selected_model,
                        confidence=j.confidence or 0.88,
                    )
                    all_matches.append(match)

                    # Update Cache
                    cache_layer.set_pair_judgment(
                        product_context,
                        rubric,
                        c_a.text,
                        c_b.text,
                        winner_cand.text,
                        j.reason,
                        j.confidence or 0.88,
                    )
                    continue

            # Fallback on LLM failure
            w_id = id_a if c_a.local_pre_rank >= c_b.local_pre_rank else id_b
            fallback_winner_cand = cand_map[w_id]
            reason = "Determined by local pre-ranking (API fallback)."
            match = MatchRecord(
                round=round_num,
                pair_id=pair_id,
                item_a_id=id_a,
                item_b_id=id_b,
                winner_id=w_id,
                reason=reason,
                source="Local fallback",
                model="fallback",
            )
            all_matches.append(match)

            # Store in cache
            cache_layer.set_pair_judgment(
                product_context,
                rubric,
                c_a.text,
                c_b.text,
                fallback_winner_cand.text,
                reason,
                confidence=0.75,
            )
            if tracker:
                tracker.record_request("judge_pair", "fallback", 0, 0, 0.0, fallback=True)

    return all_matches
