export interface Source {
  ref: number;
  file_path: string;
  start_line: number;
  end_line: number;
  symbol: string;
  kind: string;
  language: string;
  score: number;
  /** Retrievers that found this excerpt ("vector", "keyword", "identifier"); ADR 0013. */
  matched_by?: string[];
  text: string;
}

export interface QueryResponse {
  answer: string;
  sources: Source[];
}

export interface Health {
  status: "ok" | "degraded";
  ollama: { ok: boolean; llm_model?: string; embed_model?: string; missing_models?: string[]; error?: string };
  qdrant: { ok: boolean; collection?: string; indexed?: boolean; points?: number; error?: string };
  codebase_path: string;
  /** Default number of excerpts (TOP_K in .env). */
  top_k?: number;
  index_job: string;
}

export interface IndexStatus {
  state: "idle" | "running" | "done" | "error";
  full: boolean;
  started_at: string | null;
  finished_at: string | null;
  recent_progress: string[];
  report: {
    scanned: number;
    added: string[];
    updated: string[];
    deleted: string[];
    unchanged: number;
    skipped: string[];
    errors: Record<string, string>;
    chunks_written: number;
    duration_seconds: number;
  } | null;
  error: string | null;
}

const BASE = "/api";

/** Timing stats sent by the backend in the stream's `done` event. */
export interface StreamStats {
  retrieval_seconds: number | null;
  first_token_seconds: number | null;
  total_seconds: number | null;
  tokens: number;
  answer_chars: number;
}

export interface StreamHandlers {
  onSources: (sources: Source[]) => void;
  onToken: (text: string) => void;
  onHeartbeat?: (elapsedSeconds: number) => void;
  onDone: (stats: StreamStats) => void;
}

/**
 * Where a failed request broke:
 * - "backend-timeout": the backend gave up waiting for Ollama (504 with a JSON
 *   detail, or an `error` event with kind "timeout" in a stream)
 * - "gateway-timeout": a proxy in front of the backend gave up (nginx, or a port
 *   forwarder such as Codespaces): 504 without the backend's JSON body
 * - "network": the connection was dropped before any HTTP response arrived
 * - "interrupted": a stream started but the connection closed before `done`
 * - "backend": the backend reported an error inside a stream
 * - "http": any other error status
 */
export type ApiErrorKind = "backend-timeout" | "gateway-timeout" | "network" | "interrupted" | "backend" | "http";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly kind: ApiErrorKind,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isTimeout(): boolean {
    return this.kind !== "http" && this.kind !== "backend";
  }
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError((e as Error).message || "連線中斷", "network");
  }
  if (!res.ok) await throwForStatus(res);
  return res;
}

async function throwForStatus(res: Response): Promise<never> {
  let detail = `${res.status} ${res.statusText}`;
  let fromBackend = false;
  try {
    const body = await res.json();
    if (body?.detail) {
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      fromBackend = true;
    }
  } catch {
    /* not JSON: an error page from nginx or another proxy */
  }
  const kind: ApiErrorKind =
    res.status === 504 ? (fromBackend ? "backend-timeout" : "gateway-timeout") : "http";
  throw new ApiError(detail, kind, res.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await send(path, init);
  return res.json() as Promise<T>;
}

/**
 * POST /query/stream and dispatch its Server-Sent Events.
 *
 * Uses fetch + a stream reader instead of EventSource, because EventSource can
 * only send GET requests without a body. Resolves after the `done` event;
 * rejects with an ApiError on an `error` event or when the connection closes
 * early (kind "interrupted"), after the handlers have received everything that
 * arrived, so the caller can keep the partial answer.
 */
async function queryStream(
  question: string,
  top_k: number | undefined,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await send("/query/stream", {
    method: "POST",
    body: JSON.stringify({ question, top_k }),
    headers: { Accept: "text/event-stream" },
    signal,
  });
  if (!res.body) throw new ApiError("瀏覽器不支援串流回應", "http", res.status);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;

  const dispatch = (frame: string) => {
    let event = "message";
    const data: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith(":")) continue; // SSE comment
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (!data.length) return;
    const payload = JSON.parse(data.join("\n"));
    switch (event) {
      case "sources":
        handlers.onSources(payload as Source[]);
        break;
      case "token":
        handlers.onToken((payload as { text: string }).text);
        break;
      case "heartbeat":
        handlers.onHeartbeat?.((payload as { elapsed_seconds: number }).elapsed_seconds);
        break;
      case "done":
        finished = true;
        handlers.onDone(payload as StreamStats);
        break;
      case "error": {
        finished = true;
        const err = payload as { kind: string; detail: string };
        throw new ApiError(err.detail, err.kind === "timeout" ? "backend-timeout" : "backend");
      }
    }
  };

  try {
    for (;;) {
      let chunk: ReadableStreamReadResult<Uint8Array>;
      try {
        chunk = await reader.read();
      } catch (e) {
        if ((e as Error).name === "AbortError") throw e;
        throw new ApiError((e as Error).message || "連線中斷", "interrupted");
      }
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true }).replace(/\r\n?/g, "\n");
      let end: number;
      while ((end = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        dispatch(frame);
        if (finished) return;
      }
    }
    if (buffer.trim()) dispatch(buffer);
  } finally {
    reader.cancel().catch(() => undefined);
  }
  if (!finished) throw new ApiError("回答還沒傳完，連線就被關閉了", "interrupted");
}

export const api = {
  health: () => request<Health>("/health"),
  query: (question: string, top_k?: number) =>
    request<QueryResponse>("/query", { method: "POST", body: JSON.stringify({ question, top_k }) }),
  queryStream,
  startIndex: (full: boolean) => request<IndexStatus>("/index", { method: "POST", body: JSON.stringify({ full }) }),
  indexStatus: () => request<IndexStatus>("/index/status"),
};
