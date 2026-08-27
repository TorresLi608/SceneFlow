"""The consumer `generation_jobs` was built for.

The table has always provided persistence, idempotency, leases, cancel, and retry
(`app/services/job_service.py`); what it lacked was anything that drained it, so paid
generation ran inside the HTTP request instead. That had one consequence worth the whole of
this module: **Starlette does not cancel a handler when the client disconnects**, so every
"stop" button in the app hung up the browser while the provider call ran to completion and
billed. Stop, then click generate again, and the user paid twice for one image.

Moving the work here makes stopping a database operation rather than a hung-up socket:

- a job cancelled while `queued` costs nothing at all;
- a job cancelled while `running` is abandoned within a heartbeat, and — the part that
  actually saved money — its result is never written back over whatever the user did next;
- a resent POST lands on the same row, because `enqueue_job` dedupes on the target.

**In-process, not a second process.** `app/core/realtime.py` keeps its WebSocket registry in
one process's memory and `docker-compose.yml` runs a single backend container, so a worker
started elsewhere could not deliver a single `SCENE_UPDATE`. A shared broker is the
prerequisite (`docs/plans/backlog.md`), and it is one change, not this one. What the queue
buys even in-process is everything above plus surviving a restart: the row outlives the task.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable

from app.core.database import db
from app.services.job_service import (
    claim_next_job,
    fail_expired_jobs,
    finish_job,
    job_json,
    renew_lease,
)


logger = logging.getLogger(__name__)

# Three, because a prompt draft that takes two seconds should not queue behind an image that
# takes ninety. `claim_next_job` is an optimistic conditional UPDATE, so independent claim
# loops need no coordination between them — simpler than one loop with a semaphore and a
# task ledger, and it reuses concurrency safety the table already had.
WORKER_CONCURRENCY = 3
IDLE_SLEEP_SECONDS = 1.0
# Comfortably longer than a heartbeat, short enough that a killed worker's jobs settle soon.
LEASE_SECONDS = 60
HEARTBEAT_SECONDS = 20
# The lease sweep only needs to be roughly this often; expiry is what makes a job eligible.
SWEEP_SECONDS = 60
ERROR_DETAIL_CHARS = 220

# job_type -> handler. Each domain service registers its own, so this module stays ignorant
# of props, characters, and voices (`docs/architecture/boundaries.md`: services decide).
JobHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]
_handlers: dict[str, JobHandler] = {}


def register(job_type: str) -> Callable[[JobHandler], JobHandler]:
    """Bind a coroutine to a job type. The job arrives as `job_json`, never as an ORM row.

    A plain dict because the handler runs long after the claiming session closed, and holding
    a session across a provider call is the one thing the boundaries doc forbids outright.
    """

    def bind(handler: JobHandler) -> JobHandler:
        _handlers[job_type] = handler
        return handler

    return bind


def registered_types() -> frozenset[str]:
    return frozenset(_handlers)


async def dispatch(job: dict[str, Any]) -> dict[str, Any]:
    """Look up a job's handler and run it. Raises `LookupError` for an unregistered type.

    The seam between "which worker lane am I, and do I still hold the lease" and "what does
    this job actually do". Public because that second half is worth driving on its own — a
    test can run a job to completion without standing up lease renewal and a poll loop.
    """
    handler = _handlers.get(job["jobType"])
    if handler is None:
        raise LookupError(job["jobType"])
    return await handler(job) or {}


async def _beat(job_id: str, worker_id: str, task: asyncio.Task[Any]) -> None:
    """Hold the lease while `task` runs, and cancel it the moment the row says to stop.

    The renewal failing is the signal — the user hit stop, or another worker took the row
    over. Either way this worker must not keep waiting on a provider call whose result it is
    no longer entitled to write.
    """
    while not task.done():
        await asyncio.sleep(HEARTBEAT_SECONDS)
        if task.done():
            return
        with db() as session:
            still_ours = renew_lease(session, job_id, worker_id, LEASE_SECONDS)
        if not still_ours:
            logger.info("job %s lost its lease or was canceled; abandoning the call", job_id)
            task.cancel()
            return


async def _run_one(job: dict[str, Any], worker_id: str, stop: asyncio.Event) -> None:
    job_id = job["id"]
    if job["jobType"] not in _handlers:
        # Registered types are the contract; an unknown one is a deploy mistake, not a
        # provider failure, and must not sit in the queue being re-claimed forever.
        logger.error("no handler registered for job type %s (job %s)", job["jobType"], job_id)
        _settle(job_id, worker_id, error_code="NO_HANDLER", error_message=f"未注册的任务类型：{job['jobType']}")
        return

    task = asyncio.ensure_future(dispatch(job))
    beat = asyncio.ensure_future(_beat(job_id, worker_id, task))
    try:
        result = await task
    except asyncio.CancelledError:
        if stop.is_set():
            # Shutting down, not stopped by a user. Leave the row `running` — the next
            # process settles it in `fail_expired_jobs`, and swallowing the cancellation
            # here would stall the shutdown this worker is supposed to be cooperating with.
            raise
        # Cancelled by the heartbeat, i.e. the user hit stop. `cancel_job` already wrote the
        # terminal state, so writing one here would overwrite what the user asked for.
        logger.info("job %s canceled", job_id)
        return
    except Exception as exc:
        detail = str(exc)[:ERROR_DETAIL_CHARS]
        logger.warning("job %s failed: %s", job_id, detail)
        _settle(job_id, worker_id, error_code="HANDLER_FAILED", error_message=detail)
        return
    finally:
        beat.cancel()
    _settle(job_id, worker_id, result=result or {})


def _settle(
    job_id: str,
    worker_id: str,
    *,
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """Write the terminal state, tolerating a lease this worker no longer holds.

    `finish_job` refuses when the row moved on — a cancel that landed between the handler
    returning and this call. That is the correct outcome, not an error to propagate.
    """
    try:
        with db() as session:
            finish_job(
                session,
                job_id,
                worker_id,
                result=result,
                error_code=error_code,
                error_message=error_message,
            )
    except ValueError:
        logger.info("job %s was settled by someone else before this worker could", job_id)


async def _loop(worker_id: str, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            with db() as session:
                claimed = claim_next_job(session, worker_id, LEASE_SECONDS)
                job = job_json(claimed) if claimed else None
        except Exception:
            # A transient database error must not kill the loop; the queue would silently
            # stop draining and every job would look like it is still queued.
            logger.exception("could not claim a job; retrying after a pause")
            job = None
        if job is None:
            await _wait(stop, IDLE_SLEEP_SECONDS)
            continue
        await _run_one(job, worker_id, stop)


async def _sweeper(stop: asyncio.Event) -> None:
    while not stop.is_set():
        await _wait(stop, SWEEP_SECONDS)
        if stop.is_set():
            return
        try:
            fail_expired_jobs()
        except Exception:
            logger.exception("lease sweep failed; retrying on the next pass")


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    """Sleep, but wake immediately on shutdown so the process does not linger."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        return


class JobWorker:
    """Owns the worker coroutines for one process, started and stopped by the app lifespan."""

    def __init__(self, concurrency: int = WORKER_CONCURRENCY) -> None:
        self.worker_id = f"api-{os.getpid()}"
        self._concurrency = max(1, concurrency)
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    def start(self) -> None:
        if self._tasks:
            return
        if os.environ.get("SCENEFLOW_WORKER_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
            # Off for anything that drains the queue by hand — `tests/job_queue.py` claims and
            # settles the same rows, and two claimants make which one runs a job a coin flip.
            logger.info("generation job worker disabled by SCENEFLOW_WORKER_ENABLED")
            return
        # Anything the previous process left mid-flight is settled before this one claims:
        # its lease will never be renewed, and a `running` row nobody owns spins the UI.
        fail_expired_jobs()
        self._stop = asyncio.Event()
        self._tasks = [
            asyncio.create_task(_loop(f"{self.worker_id}-{index}", self._stop), name=f"job-worker-{index}")
            for index in range(self._concurrency)
        ]
        self._tasks.append(asyncio.create_task(_sweeper(self._stop), name="job-lease-sweeper"))
        logger.info("generation job worker started id=%s lanes=%d", self.worker_id, self._concurrency)

    async def stop(self) -> None:
        if not self._tasks:
            return
        self._stop.set()
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("generation job worker stopped id=%s", self.worker_id)


worker = JobWorker()
