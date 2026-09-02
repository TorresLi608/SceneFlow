"""Cooperative cancellation for the background renders a project can have in flight.

A render is started with `asyncio.create_task` inside the API process (see
`docs/architecture/boundaries.md` — the `generation_jobs` worker is the intended home for
this and does not exist yet), so there is nothing durable to cancel through. What a user
clicking 停止 actually needs is for the run to stop *before it bills them for the next
shot*, which is a check between units of work rather than an interrupt.

So: one event per project, set by the cancel endpoint, polled by the run loop. Shots
already in flight finish and are kept — throwing away an image the provider has already
charged for helps nobody — and the run reports a terminal status the same way a completed
one does.

Same in-process limitation as `app/core/realtime.py`: this registry lives in one worker's
memory, so a second backend process would not see the flag. Both would need a shared broker
before the app can run multi-process, and that is one change, not two.
"""

from __future__ import annotations

import asyncio
import logging


logger = logging.getLogger(__name__)

# project id -> the flag its running render polls. Present only while a run is registered.
_cancellations: dict[str, asyncio.Event] = {}
_tasks: dict[str, asyncio.Task[object]] = {}


def register(project_id: str) -> asyncio.Event:
    """Arm a fresh cancel flag for a run that is about to start.

    Always a new event rather than a reused one: a stale flag left set by a previous
    cancellation would stop the next run before it rendered anything.
    """
    event = asyncio.Event()
    _cancellations[project_id] = event
    return event


def release(project_id: str, event: asyncio.Event | None = None) -> None:
    """Drop the flag once the run is over.

    The identity check matters: by the time a cancelled run finishes unwinding, the user
    may already have started a new one, and clearing the map blindly would discard the new
    run's flag and leave it uncancellable.
    """
    current = _cancellations.get(project_id)
    if current is None or (event is not None and current is not event):
        return
    _cancellations.pop(project_id, None)
    _tasks.pop(project_id, None)


def attach_task(project_id: str, event: asyncio.Event, task: asyncio.Task[object]) -> None:
    """Associate the background task so stop can interrupt an in-flight provider call."""
    if _cancellations.get(project_id) is event:
        _tasks[project_id] = task


def cancel(project_id: str) -> bool:
    """Ask the project's running render to stop. False when nothing is running."""
    event = _cancellations.get(project_id)
    if event is None:
        return False
    event.set()
    task = _tasks.get(project_id)
    if task and not task.done():
        task.cancel()
    logger.info("cancellation requested project=%s", project_id)
    return True


def is_cancelled(event: asyncio.Event | None) -> bool:
    """Convenience for run loops, which hold an optional event."""
    return event is not None and event.is_set()
