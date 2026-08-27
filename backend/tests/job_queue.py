"""Drive the generation-job queue from a synchronous test.

Paid generation is queued rather than awaited in the request (see
`app/services/job_worker.py` for why: Starlette does not cancel a handler when the client
disconnects, so a stop button could only ever hang up the browser while the provider call ran
on and billed). That makes the endpoints 202s, and a test that wants to assert on the *result*
has to run the work itself.

This runs the same code path the worker does — `claim_next_job` → `dispatch` → `finish_job` —
just without the lease-renewal loop and the poll interval. So a test still exercises the real
handler, the real claim, and the real terminal write.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

# Importing this module means the test drives the queue itself, so the in-process worker the
# app lifespan would otherwise start must stay down: two claimants racing for the same row
# makes which one runs a job — and therefore whether `drain_one` sees it — a coin flip. Set
# before `app.main` is imported, which every test does lazily inside its fixture.
os.environ.setdefault("SCENEFLOW_WORKER_ENABLED", "0")

from app.core.database import db  # noqa: E402
from app.services.job_service import claim_next_job, finish_job, job_json  # noqa: E402
from app.services.job_worker import dispatch  # noqa: E402


def drain_jobs(limit: int = 20) -> list[dict[str, Any]]:
    """Run every queued job to a terminal state and return them, oldest first.

    A failing handler settles the job as `failed` rather than raising, exactly as the worker
    would — a test asserting on provider failure wants to read the row, not catch an
    exception. `limit` stops a handler that enqueues more work from spinning forever.
    """
    settled: list[dict[str, Any]] = []
    for _ in range(limit):
        worker_id = f"test-worker-{len(settled)}"
        with db() as session:
            claimed = claim_next_job(session, worker_id)
            job = job_json(claimed) if claimed else None
        if job is None:
            break
        try:
            result = asyncio.run(dispatch(job))
        except Exception as exc:  # noqa: BLE001 -- mirrors the worker: any failure settles the row
            with db() as session:
                settled.append(
                    job_json(
                        finish_job(
                            session,
                            job["id"],
                            worker_id,
                            error_code="HANDLER_FAILED",
                            error_message=str(exc)[:220],
                        )
                    )
                )
            continue
        with db() as session:
            settled.append(job_json(finish_job(session, job["id"], worker_id, result=result)))
    return settled


def drain_one(limit: int = 20) -> dict[str, Any]:
    """`drain_jobs` for the common case of a test that queued exactly one job."""
    settled = drain_jobs(limit)
    assert len(settled) == 1, f"expected exactly one job, drained {len(settled)}"
    return settled[0]


def succeeded(job: dict[str, Any]) -> dict[str, Any]:
    """The job's result, with a readable failure when the handler did not get that far."""
    assert job["status"] == "succeeded", f"job {job['jobType']} failed: {job['errorMessage']}"
    return job["result"] or {}
