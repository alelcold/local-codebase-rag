import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type Health, type IndexStatus, type QueryResponse, type Source } from "./api";

const EXAMPLES = [
  "玩家受傷後的無敵時間在哪裡設定？",
  "分數是怎麼計算和顯示的？",
  "遊戲主迴圈的流程是什麼？",
];

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [indexStatus, setIndexStatus] = useState<IndexStatus | null>(null);
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(8);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<QueryError | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [asked, setAsked] = useState("");
  const [openRefs, setOpenRefs] = useState<Set<number>>(new Set());

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await api.health());
      setHealthError(null);
    } catch (e) {
      setHealthError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    refreshHealth();
    api.indexStatus().then(setIndexStatus).catch(() => undefined);
  }, [refreshHealth]);

  // Count seconds while a query is in flight, so slow CPU-only answers do not look frozen.
  useEffect(() => {
    if (!loading) return;
    const started = Date.now();
    setElapsed(0);
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [loading]);

  // Poll while an indexing job runs.
  useEffect(() => {
    if (indexStatus?.state !== "running") return;
    const timer = setInterval(async () => {
      try {
        const status = await api.indexStatus();
        setIndexStatus(status);
        if (status.state !== "running") refreshHealth();
      } catch {
        /* keep polling */
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [indexStatus?.state, refreshHealth]);

  const startIndex = async (full: boolean) => {
    if (full && !confirm("完整重建會清除目前的索引並重新處理所有檔案，確定嗎？")) return;
    try {
      setIndexStatus(await api.startIndex(full));
    } catch (e) {
      alert(`無法開始索引：${(e as Error).message}`);
    }
  };

  const ask = async (q: string) => {
    const text = q.trim();
    if (!text || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setAsked(text);
    setOpenRefs(new Set());
    const started = Date.now();
    try {
      setResult(await api.query(text, topK));
    } catch (e) {
      setError({ error: e as Error, seconds: Math.round((Date.now() - started) / 1000) });
    } finally {
      setLoading(false);
    }
  };

  const showSource = (ref: number) => {
    setOpenRefs((prev) => new Set(prev).add(ref));
    requestAnimationFrame(() =>
      document.getElementById(`source-${ref}`)?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  };

  const toggleSource = (ref: number) =>
    setOpenRefs((prev) => {
      const next = new Set(prev);
      if (next.has(ref)) next.delete(ref);
      else next.add(ref);
      return next;
    });

  const indexing = indexStatus?.state === "running";

  return (
    <div className="page">
      <header className="topbar">
        <div>
          <h1>Codebase RAG</h1>
          <p className="muted">用自然語言查詢專案程式碼（全部在本機執行）</p>
        </div>
        <HealthBadge health={health} error={healthError} onRefresh={refreshHealth} />
      </header>

      <section className="card index-card">
        <div className="index-row">
          <div>
            <strong>索引</strong>
            <span className="muted">
              {health?.qdrant.indexed ? ` ${health.qdrant.points} 個片段` : " 尚未建立"}
              {health ? ` · ${health.codebase_path}` : ""}
            </span>
          </div>
          <div className="buttons">
            <button onClick={() => startIndex(false)} disabled={indexing}>
              {indexing ? "索引中…" : "更新索引"}
            </button>
            <button className="secondary" onClick={() => startIndex(true)} disabled={indexing}>
              完整重建
            </button>
          </div>
        </div>
        <IndexSummary status={indexStatus} />
      </section>

      <form
        className="card ask"
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
      >
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask(question);
          }}
          placeholder="例如：玩家跳躍的邏輯寫在哪裡？（⌘/Ctrl + Enter 送出）"
          rows={3}
        />
        <div className="ask-row">
          <div className="examples">
            {EXAMPLES.map((ex) => (
              <button
                type="button"
                key={ex}
                className="chip"
                onClick={() => {
                  setQuestion(ex);
                  ask(ex);
                }}
              >
                {ex}
              </button>
            ))}
          </div>
          <label className="topk">
            參考片段
            <select value={topK} onChange={(e) => setTopK(Number(e.target.value))}>
              {[4, 6, 8, 12, 16].map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={loading || !question.trim()}>
            {loading ? `生成中… ${elapsed}s` : "送出"}
          </button>
        </div>
      </form>

      {loading && <Generating seconds={elapsed} />}
      {error && <QueryErrorCard error={error} />}

      {result && (
        <>
          <section className="card">
            <div className="question">Q：{asked}</div>
            <Answer text={result.answer} onRef={showSource} />
          </section>

          {result.sources.length > 0 && (
            <section className="sources">
              <h2>引用的程式碼</h2>
              {result.sources.map((s) => (
                <SourceCard key={s.ref} source={s} open={openRefs.has(s.ref)} onToggle={() => toggleSource(s.ref)} />
              ))}
            </section>
          )}
        </>
      )}
    </div>
  );
}

interface QueryError {
  error: Error;
  /** How long the request ran before it failed. */
  seconds: number;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds} 秒`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s ? `${m} 分 ${s} 秒` : `${m} 分`;
}

function Generating({ seconds }: { seconds: number }) {
  return (
    <div className="card generating" role="status" aria-live="polite">
      <div className="generating-head">
        <span className="spinner" aria-hidden="true" />
        <strong>生成中</strong>
        <span className="muted">已等待 {formatDuration(seconds)}</span>
      </div>
      <p className="muted small">
        本機模型正在閱讀相關程式碼並產生回答。第一次查詢需要載入模型；只有 CPU 的環境（例如 Codespaces）一次查詢可能要
        1～2 分鐘，請耐心等候。
      </p>
    </div>
  );
}

function QueryErrorCard({ error: { error, seconds } }: { error: QueryError }) {
  if (!(error instanceof ApiError) || !error.isTimeout) {
    return <div className="card error">查詢失敗：{error.message}</div>;
  }
  const title =
    error.kind === "backend-timeout"
      ? "查詢逾時：後端等不到模型回應"
      : error.kind === "gateway-timeout"
        ? "查詢逾時：前端代理先中斷了連線"
        : "查詢中斷：連線在收到回應前被關閉";
  return (
    <div className="card error timeout">
      <strong>{title}</strong>
      <p className="small">
        等待 {formatDuration(seconds)} 後失敗。{error.kind === "backend-timeout" ? error.message : `（${error.message}）`}
      </p>
      <p className="small">可能原因與處理方式：</p>
      <ul className="small">
        <li>
          <strong>沒有 GPU，模型推論很慢</strong>（例如 Codespaces）：改用較小的模型（如 <code>qwen2.5-coder:3b</code>
          ），或把「參考片段」調少。
        </li>
        <li>
          <strong>第一次查詢正在載入模型</strong>：稍候再問一次，模型載入後會快很多（可用 <code>ollama ps</code> 確認）。
        </li>
        <li>
          <strong>逾時設定太短</strong>：在 <code>.env</code> 調高 <code>LLM_REQUEST_TIMEOUT</code>（後端等 Ollama）與{" "}
          <code>PROXY_READ_TIMEOUT</code>（nginx 等後端），兩者都預設 300 秒，再執行 <code>docker compose up -d</code>。
        </li>
        {error.kind !== "backend-timeout" && (
          <li>
            <strong>透過 Codespaces 或其他轉發／反向代理連線</strong>：中間的代理可能有自己的逾時上限，調高上面的設定也無效。可改用{" "}
            <code>curl</code> 直接呼叫後端 <code>http://localhost:8000/query</code> 確認是否為代理造成。
          </li>
        )}
      </ul>
    </div>
  );
}

function HealthBadge({ health, error, onRefresh }: { health: Health | null; error: string | null; onRefresh: () => void }) {
  let label = "檢查中…";
  let tone = "pending";
  let detail = "";
  if (error) {
    label = "後端無法連線";
    tone = "bad";
    detail = error;
  } else if (health) {
    const problems: string[] = [];
    if (!health.ollama.ok) {
      problems.push(
        health.ollama.error
          ? `Ollama 無法連線：${health.ollama.error}`
          : `缺少模型：${health.ollama.missing_models?.join(", ")}（請執行 ollama pull）`,
      );
    }
    if (!health.qdrant.ok) problems.push(`Qdrant 無法連線：${health.qdrant.error}`);
    tone = problems.length ? "bad" : "good";
    label = problems.length ? "服務異常" : `${health.ollama.llm_model} · ${health.ollama.embed_model}`;
    detail = problems.join("\n");
  }
  return (
    <button className={`badge ${tone}`} title={detail || "點擊重新檢查"} onClick={onRefresh} type="button">
      <span className="dot" />
      {label}
    </button>
  );
}

function IndexSummary({ status }: { status: IndexStatus | null }) {
  if (!status || status.state === "idle") return null;
  if (status.state === "running") {
    const last = status.recent_progress[status.recent_progress.length - 1];
    return <p className="muted small">{status.full ? "完整重建中" : "增量索引中"}… {last ?? ""}</p>;
  }
  if (status.state === "error") return <p className="error small">索引失敗：{status.error}</p>;
  const r = status.report;
  if (!r) return null;
  const errors = Object.entries(r.errors);
  return (
    <div className="small">
      <p className="muted">
        完成（{r.duration_seconds}s）：掃描 {r.scanned}、新增 {r.added.length}、更新 {r.updated.length}、刪除{" "}
        {r.deleted.length}、未變更 {r.unchanged}
        {r.skipped.length ? `、略過（檔案過大）${r.skipped.length}` : ""}
      </p>
      {errors.length > 0 && (
        <ul className="error">
          {errors.map(([path, msg]) => (
            <li key={path}>
              {path}：{msg}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Minimal Markdown: fenced code blocks, inline code, bold, and clickable [n] citations. */
function Answer({ text, onRef }: { text: string; onRef: (ref: number) => void }) {
  const parts = text.split(/```(\w*)\n?([\s\S]*?)```/g);
  const nodes = [];
  for (let i = 0; i < parts.length; i += 3) {
    if (parts[i]) nodes.push(<Prose key={`p${i}`} text={parts[i]} onRef={onRef} />);
    if (i + 2 < parts.length) {
      nodes.push(
        <pre key={`c${i}`} className="code">
          <code>{parts[i + 2].replace(/\n$/, "")}</code>
        </pre>,
      );
    }
  }
  return <div className="answer">{nodes}</div>;
}

function Prose({ text, onRef }: { text: string; onRef: (ref: number) => void }) {
  const tokens = text.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*|\[\d+\])/g);
  return (
    <div className="prose">
      {tokens.map((tok, i) => {
        if (/^`[^`]+`$/.test(tok)) return <code key={i}>{tok.slice(1, -1)}</code>;
        if (/^\*\*[^*]+\*\*$/.test(tok)) return <strong key={i}>{tok.slice(2, -2)}</strong>;
        const ref = tok.match(/^\[(\d+)\]$/);
        if (ref) {
          return (
            <button key={i} type="button" className="cite" onClick={() => onRef(Number(ref[1]))}>
              {tok}
            </button>
          );
        }
        return <span key={i}>{tok}</span>;
      })}
    </div>
  );
}

function SourceCard({ source, open, onToggle }: { source: Source; open: boolean; onToggle: () => void }) {
  const lines = source.text.split("\n");
  return (
    <div className="card source" id={`source-${source.ref}`}>
      <button type="button" className="source-head" onClick={onToggle} aria-expanded={open}>
        <span className="ref">[{source.ref}]</span>
        <span className="path">
          {source.file_path}
          <span className="lines">
            :{source.start_line}-{source.end_line}
          </span>
        </span>
        {source.symbol && <span className="symbol">{source.symbol}</span>}
        <span className="score" title="相似度分數">
          {source.score.toFixed(3)}
        </span>
        <span className="chevron">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <pre className="code numbered">
          {lines.map((line, i) => (
            <div key={i} className="line">
              <span className="ln">{source.start_line + i}</span>
              <span>{line || " "}</span>
            </div>
          ))}
        </pre>
      )}
    </div>
  );
}
