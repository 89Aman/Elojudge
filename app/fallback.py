"""Default rubric and precomputed demo result for offline fallback."""

from __future__ import annotations

from app.schemas import Rubric, RubricDimension


# ── Default rubric ───────────────────────────────────────────────────────────

DEFAULT_RUBRIC = Rubric(
    dimensions=[
        RubricDimension(
            name="Core-goal impact",
            weight=0.4,
            description="How strongly the request advances the stated product goals.",
        ),
        RubricDimension(
            name="User value / frequency signal",
            weight=0.25,
            description="Expected breadth and urgency of user benefit.",
        ),
        RubricDimension(
            name="Delivery feasibility",
            weight=0.2,
            description="Higher score means easier or lower-risk to deliver.",
        ),
        RubricDimension(
            name="Product-fit",
            weight=0.15,
            description="Consistency with product positioning and constraints.",
        ),
    ]
)


