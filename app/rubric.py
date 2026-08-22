"""LLM rubric generation with exact caching, validation, and fallback."""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from google import genai

from app.budget import JobBudget
from app.cache import cache_layer
from app.config import settings
from app.fallback import DEFAULT_RUBRIC
from app.observability import ObservabilityTracker, estimate_tokens
from app.schemas import Rubric, RubricDimension
from app.utils import extract_json

logger = logging.getLogger(__name__)


# ── Prompt ───────────────────────────────────────────────────────────────────

RUBRIC_PROMPT = """You are a product prioritization expert. Given a product description, create a rubric for evaluating feature requests.

Product description:
{product_context}

Return ONLY valid JSON in this exact structure:
{{
  "dimensions": [
    {{
      "name": "Dimension name",
      "weight": 0.4,
      "description": "What this dimension measures"
    }}
  ]
}}

Rules:
- Exactly 3 to 5 dimensions.
- Weights must be positive numbers that sum to 1.0.
- Tailor dimensions to this specific product's goals.
- Keep descriptions concise (one sentence each)."""


# ── Validation ───────────────────────────────────────────────────────────────

def validate_rubric_data(data: dict) -> Optional[Rubric]:
    """Validate and normalize raw dictionary into a Rubric object."""
    try:
        dims = data.get("dimensions", [])
        if not (3 <= len(dims) <= 5):
            return None

        rubric_dims = []
        for d in dims:
            if not all(k in d for k in ("name", "weight", "description")):
                return None
            weight = float(d["weight"])
            if weight < 0:
                return None
            rubric_dims.append(
                RubricDimension(
                    name=str(d["name"]).strip(),
                    weight=weight,
                    description=str(d["description"]).strip(),
                )
            )

        total = sum(d.weight for d in rubric_dims)
        if total <= 0:
            return None

        for d in rubric_dims:
            d.weight = round(d.weight / total, 4)

        return Rubric(dimensions=rubric_dims)

    except Exception as e:
        logger.warning("Rubric validation error: %s", e)
        return None


# ── Generation Pipeline ──────────────────────────────────────────────────────

async def generate_rubric(
    product_context: str,
    budget: JobBudget,
    tracker: Optional[ObservabilityTracker] = None,
    api_key: Optional[str] = None,
) -> tuple[Rubric, bool]:
    """Retrieve cached rubric or generate one via LLM.

    Returns:
        (rubric, is_fallback)
    """
    # 1. Exact Cache Check
    cached = cache_layer.get_rubric(product_context)
    if cached:
        logger.info("Rubric exact cache hit")
        if tracker:
            tracker.record_request("generate_rubric", "cache", 0, 0, 0.0, cache_hit=True)
        return cached, False

    # 2. Budget Check
    if not budget.can_make_request():
        logger.warning("Budget exhausted, using default rubric")
        if tracker:
            tracker.record_request("generate_rubric", "fallback", 0, 0, 0.0, fallback=True)
        return DEFAULT_RUBRIC, True

    # 3. LLM Request
    t0 = time.time()
    prompt = RUBRIC_PROMPT.format(product_context=product_context)
    input_tokens = estimate_tokens(prompt)
    model = settings.model_cheap
    active_key = api_key or settings.api_key

    try:
        if not active_key:
            logger.warning("No API key configured, using default rubric")
            return DEFAULT_RUBRIC, True

        client = genai.Client(api_key=active_key)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=1024,
                response_mime_type="application/json",
            ),
        )

        latency_ms = (time.time() - t0) * 1000.0
        raw_text = response.text.strip()
        output_tokens = estimate_tokens(raw_text)

        # Record budget usage
        budget.record_usage(input_tokens=input_tokens, output_tokens=output_tokens)
        cost = budget.calculate_cost(input_tokens, output_tokens)

        if tracker:
            tracker.record_request("generate_rubric", model, input_tokens, output_tokens, latency_ms, cost=cost)

        json_str = extract_json(raw_text)
        data = json.loads(json_str)
        rubric = validate_rubric_data(data)

        if rubric:
            cache_layer.set_rubric(product_context, rubric)
            return rubric, False

        logger.warning("Generated rubric failed validation, using default")
        return DEFAULT_RUBRIC, True

    except Exception as e:
        latency_ms = (time.time() - t0) * 1000.0
        logger.warning("Rubric generation failed (%s), using default", e)
        if tracker:
            tracker.record_request("generate_rubric", model, input_tokens, 0, latency_ms, fallback=True)
        return DEFAULT_RUBRIC, True
