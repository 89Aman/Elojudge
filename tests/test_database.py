"""Unit tests for DigitalOcean PostgreSQL database storage."""

import pytest
from app.database import (
    get_db_pool,
    init_db,
    save_ranking_job,
    get_job_by_id,
    get_recent_jobs,
    record_user_usage_in_db,
    get_user_daily_usage_from_db,
    close_db,
)


@pytest.mark.anyio
async def test_db_job_save_and_retrieve():
    await init_db()
    pool = await get_db_pool()
    if not pool:
        pytest.skip("DigitalOcean DB pool not available")

    test_job_id = "test_job_unit_12345"
    saved = await save_ranking_job(
        job_id=test_job_id,
        user_email="testuser@example.com",
        user_ip="127.0.0.1",
        product_context="Test Product Context for Unit Testing",
        raw_items_count=5,
        clean_items_count=4,
        ranked_items_count=4,
        summary_dict={"test": "summary", "cost": 0.001},
        rubric_dict={"dimensions": [{"name": "Impact", "weight": 0.5}]},
        ranked_items_list=[{"rank": 1, "id": "item1", "text": "Feature A", "elo": 1250}],
        lower_priority_list=[],
        matches_list=[],
        cost_estimate=0.001,
        is_byok=False,
    )
    assert saved is True

    # Retrieve
    job = await get_job_by_id(test_job_id)
    assert job is not None
    assert job["id"] == test_job_id
    assert job["user_email"] == "testuser@example.com"
    assert job["ranked_items_count"] == 4
    assert len(job["ranked_items"]) == 1

    # Check recent jobs list
    jobs = await get_recent_jobs(limit=5, user_email="testuser@example.com")
    assert len(jobs) >= 1
    assert any(j["id"] == test_job_id for j in jobs)

    # Test usage logging
    await record_user_usage_in_db("testuser@example.com", is_google=True, is_byok=False)
    usage = await get_user_daily_usage_from_db("testuser@example.com")
    assert usage is not None
    assert usage >= 1
