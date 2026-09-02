/**
 * The client half of the generation-job queue.
 *
 * Paid generation used to run inside the POST, which meant a "stop" button could only abort
 * the browser's request — Starlette does not cancel a handler on client disconnect, so the
 * provider call ran on and billed anyway (see `backend/app/services/job_worker.py`). Those
 * endpoints now return `202 {job}` and the work happens in a worker.
 *
 * `runJob` keeps that change invisible to callers: it enqueues, polls until the row is
 * terminal, and returns the handler's result, so an action that used to await a provider
 * still awaits one value. What changed is what an `AbortSignal` now does — it cancels the
 * *job*, which is a database write the worker acts on within a heartbeat. That is the whole
 * point of the queue, so a caller that passes a signal gets a stop that actually stops.
 */

import { isCancel } from "axios";

import { httpClient } from "@/lib/http/client";

/** Statuses in which the row is still doing work. Anything else is terminal. */
const UNFINISHED = new Set(["queued", "running"]);

/**
 * Fast enough that a two-second prompt draft does not feel queued, slow enough that a
 * ninety-second image does not cost a hundred requests. Backed off below.
 */
const FIRST_POLL_MS = 400;
const MAX_POLL_MS = 3_000;

export interface GenerationJob {
  id: string;
  projectId: string;
  episodeId: string | null;
  sceneId: string | null;
  jobType: string;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled";
  progress: number;
  result: Record<string, unknown> | null;
  attempt: number;
  maxAttempts: number;
  errorCode: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface JobResponse {
  job: GenerationJob;
}

/** Thrown when a job settles as `failed`, carrying what the worker recorded. */
export class JobFailedError extends Error {
  readonly code: string | null;
  readonly job: GenerationJob;

  constructor(job: GenerationJob) {
    super(job.errorMessage || "generation job failed");
    this.name = "JobFailedError";
    this.code = job.errorCode;
    this.job = job;
  }
}

/** Thrown when the job settled as `canceled` — by this caller's signal or another tab's. */
export class JobCanceledError extends Error {
  constructor() {
    super("generation job canceled");
    this.name = "JobCanceledError";
  }
}

export async function getJobAction(jobID: string, signal?: AbortSignal) {
  const response = await httpClient.get<JobResponse>(`/api/bff/jobs/${jobID}`, { signal });
  return response.data.job;
}

export async function cancelJobAction(jobID: string) {
  const response = await httpClient.post<JobResponse>(`/api/bff/jobs/${jobID}/cancel`);
  return response.data.job;
}

export async function retryJobAction(jobID: string) {
  const response = await httpClient.post<JobResponse>(`/api/bff/jobs/${jobID}/retry`);
  return response.data.job;
}

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

/**
 * Poll a job to a terminal state and return its result.
 *
 * The poll deliberately carries no abort signal of its own: aborting the *poll* would leave
 * the job running and billing, which is the bug this queue exists to fix. The signal cancels
 * the job instead, and the loop then reads the canceled row like any other terminal state.
 */
export async function awaitJob<T>(job: GenerationJob, signal?: AbortSignal): Promise<T> {
  let current = job;
  let delay = FIRST_POLL_MS;

  const stop = () => {
    // Fire-and-forget: the loop learns the outcome from the next poll, and a failed cancel
    // must not mask the job's own result.
    void cancelJobAction(current.id).catch(() => undefined);
  };
  if (signal?.aborted) stop();
  signal?.addEventListener("abort", stop, { once: true });

  try {
    while (UNFINISHED.has(current.status)) {
      await sleep(delay);
      delay = Math.min(delay * 2, MAX_POLL_MS);
      current = await getJobAction(current.id);
    }
  } finally {
    signal?.removeEventListener("abort", stop);
  }

  if (current.status === "canceled") throw new JobCanceledError();
  if (current.status !== "succeeded") throw new JobFailedError(current);
  return (current.result ?? {}) as T;
}

/** Enqueue and await in one call, for an action that used to await the provider directly. */
export async function runJob<T>(enqueue: Promise<{ job: GenerationJob }>, signal?: AbortSignal): Promise<T> {
  const { job } = await enqueue;
  return awaitJob<T>(job, signal);
}

/**
 * "The user stopped this" — for an `onError` that should stay quiet rather than raise a toast.
 *
 * Covers both shapes, because a page usually has some calls still going straight to the
 * provider and some going through the queue: an aborted request is an axios cancel, while an
 * aborted *job* settles server-side and comes back as `JobCanceledError`.
 */
export function isCanceled(error: unknown): boolean {
  return error instanceof JobCanceledError || isCancel(error);
}
