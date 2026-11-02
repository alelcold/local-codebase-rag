# Knowledge checklist

> English first; 繁體中文版本在下方.
> For each topic: a plain explanation, where it lives in this repo, likely interview questions, and a self-check. Tick a box only when you can explain it **without notes**.

## 1. RAG (Retrieval-Augmented Generation)

**Plain explanation**: An LLM does not know your codebase. RAG first **retrieves** the most relevant pieces of your own data, pastes them into the prompt, and then asks the LLM to answer **using only those pieces**. The model's job shifts from remembering to reading and explaining.

**In this repo**:
- `backend/app/rag.py`: `RagService.retrieve()` embeds the question and searches Qdrant. `build_prompt()` numbers the excerpts `[1]…[n]` with `file:start-end`. `RagService.answer()` calls the LLM.
- `SYSTEM_PROMPT` in the same file tells the model to answer only from the excerpts and to cite them.

**Interview questions**:
- Walk through what happens between a user's question and the answer.
- Why use RAG instead of fine-tuning the model on the codebase?
- How do you reduce hallucinations in a RAG system?
- What happens when the answer is not in the retrieved chunks?

**Self-check**:
- [ ] I can draw the index-time and query-time flows from memory.
- [ ] I can explain RAG vs. fine-tuning vs. long-context prompting.
- [ ] I can point to the line where retrieved chunks enter the prompt.

## 2. Embeddings

**Plain explanation**: An embedding model turns text into a list of numbers (a vector) so that texts with similar meaning end up close together. "Where does the player jump?" lands near the `Player.update` code. Closeness is usually measured by cosine similarity.

**In this repo**:
- `backend/app/indexer.py`: `embed_text()` builds the text that gets embedded (file path + symbol header + code). `_index_file()` embeds in batches.
- `backend/app/config.py`: `query_prefix` / `doc_prefix`. nomic expects `search_query:` for questions and `search_document:` for documents.
- `backend/app/services.py`: `OllamaEmbedding` setup. `EMBED_MODEL` selects the model.

**Interview questions**:
- What is an embedding, and what does cosine similarity measure?
- Why must queries and documents use the same embedding model?
- What happens if you switch the embedding model without re-indexing? (In this repo, the collection name is derived from the model name.)
- Why do some models use different prefixes for queries and documents?

**Self-check**:
- [ ] I can explain vector similarity with a 2-D example.
- [ ] I know why the collection name contains the embedding model name.
- [ ] I can explain the bug where empty env vars disabled the nomic prefixes.

## 3. Chunking

**Plain explanation**: Documents are too big to embed or send whole, so they are cut into chunks. Chunks that are too small lose context, and chunks that are too large blur the meaning and waste prompt space. For code, the best chunks follow the **syntax**: one function or class per chunk.

**In this repo**:
- `backend/app/chunker.py`: tree-sitter for TS/JS (`_chunk_js`, `_split_class`), heading-based Markdown splitting (`_chunk_markdown`), and line windows as a fallback (`_window_chunks`).
- `backend/tests/test_chunker.py`: checks line-number accuracy and the splitting rules.
- ADR [0004](../decisions/0004-chunking-by-file-type.md).

**Interview questions**:
- How did you choose the chunk size? What are the trade-offs?
- Why chunk by syntax tree instead of fixed-size windows?
- How do you keep accurate line numbers for citations?
- How do you handle a 500-line class?

**Self-check**:
- [ ] I can explain what tree-sitter is and why it beats regex here.
- [ ] I can describe what happens to JSDoc, imports and oversized classes.
- [ ] I know why the file hash includes `CHUNK_MAX_CHARS`.

## 4. Vector databases

**Plain explanation**: A vector database stores vectors plus metadata and can quickly find the vectors nearest to a query vector, usually with an approximate index such as HNSW. Metadata filters (for example `file_path == X`) let you search or delete subsets.

**In this repo**:
- `backend/app/store.py`: `CodeVectorStore`. `query()` does similarity search; `file_hashes()` scrolls the payloads for incremental indexing; `delete_file()` deletes by filter; `_store()` works around the wrapper's construction-time detection.
- `docker-compose.yml`: the Qdrant service and the `qdrant_data` volume.
- ADR [0003](../decisions/0003-qdrant-vector-database.md).

**Interview questions**:
- Why use a vector DB instead of storing vectors in Postgres or a NumPy array?
- What is approximate nearest-neighbor search (e.g. HNSW), and what does "approximate" cost you?
- How does incremental indexing work here? What is the source of truth?
- Describe a bug you hit with the vector store and how you found it.

**Self-check**:
- [ ] I can compare Qdrant, Chroma, pgvector and FAISS in one sentence each.
- [ ] I can explain the `text-dense` bug and why unit tests missed it.
- [ ] I can explain payload indexes and why `file_path` has one.

## 5. Model quantization

**Plain explanation**: Model weights are normally 16-bit numbers. Quantization stores them in fewer bits (for example 4-bit), which cuts memory about 4× and speeds up inference, at a small cost in quality. Ollama's default tags (such as `Q4_K_M`) are 4-bit quantized.

**In this repo**:
- `.env.example`: `LLM_MODEL`. The `qwen2.5-coder:14b` tag is about 9 GB because it is Q4.
- ADR [0005](../decisions/0005-model-selection-and-hardware.md): the size table.

**Interview questions**:
- Roughly how much memory does a 14B model need at FP16 vs. Q4?
- What quality loss does quantization cause, and when does it matter?
- What do names like `Q4_K_M` and `Q8_0` mean, roughly?

**Self-check**:
- [ ] I can estimate model memory: parameters × bits ÷ 8 (+ overhead).
- [ ] I can explain why Q4 is a common sweet spot for local inference.

## 6. Model size vs. hardware

**Plain explanation**: Model memory is **weights + KV cache + overhead**. The KV cache grows with context length. Generation speed depends mostly on memory bandwidth. On Apple Silicon the GPU and CPU share unified memory, but macOS only lets the GPU use part of it by default.

**In this repo**:
- `backend/app/services.py`: `context_window=settings.llm_num_ctx` is sent to Ollama as `num_ctx`.
- `.env.example`: `LLM_NUM_CTX`, `OLLAMA_KEEP_ALIVE`.
- ADR [0005](../decisions/0005-model-selection-and-hardware.md); `docs/metrics.md`, model comparison table.

**Interview questions**:
- Why did you pick 14B for a 32 GB Mac and not 32B?
- What is the KV cache, and why does a long RAG prompt need more memory?
- What limits tokens per second on a laptop?
- What happens if `num_ctx` is too small? (Retrieved code gets truncated silently.)

**Self-check**:
- [ ] I can do the 3B / 14B / 32B memory estimate on a whiteboard.
- [ ] I measured actual memory with `ollama ps` and recorded it in metrics.

## 7. Docker networking (`host.docker.internal` / `host-gateway`)

**Plain explanation**: Inside a container, `localhost` means the container itself, not your computer. To reach a service on the host, Docker Desktop provides the name `host.docker.internal`. On Linux you add it yourself with `extra_hosts: host.docker.internal:host-gateway`, and the host service must listen on an interface the container can reach (`0.0.0.0`, not `127.0.0.1`).

**In this repo**:
- `docker-compose.yml`: `extra_hosts` on the backend; `OLLAMA_BASE_URL=http://host.docker.internal:11434`.
- `frontend/nginx.conf.template`: `proxy_pass http://backend:8000/` uses Compose service-name DNS.
- [devlog 2026-11-01](../devlog/2026-11-01.md); ADR [0006](../decisions/0006-multi-environment-deployment.md).

**Interview questions**:
- Why can't the backend container call `http://localhost:11434`?
- How do containers in the same Compose project find each other?
- Why did Codespaces need `OLLAMA_HOST=0.0.0.0` when the Mac did not?
- What are the security implications of binding to `0.0.0.0`?

**Self-check**:
- [ ] I can explain network namespaces and loopback in one minute.
- [ ] I can debug "connection refused" from a container step by step.

## 8. Apple Silicon and Docker GPU limits

**Plain explanation**: Docker on a Mac runs containers inside a Linux VM, and Apple's Metal GPU is not exposed to that VM. Anything GPU-heavy, such as LLM inference, should therefore run natively on macOS. On Linux with NVIDIA GPUs, containers can use the GPU through the NVIDIA Container Toolkit, which is a different situation.

**In this repo**:
- Compose has no Ollama service by design. `scripts/setup.sh` checks and starts Ollama on the host.
- ADR [0002](../decisions/0002-ollama-outside-docker-on-mac.md); README section "為什麼 Ollama 不放在 Docker 裡".

**Interview questions**:
- Why is Ollama not in your docker-compose file?
- How would this differ on a Linux server with an NVIDIA GPU?
- What is unified memory, and why does it matter for local LLMs?

**Self-check**:
- [ ] I can explain the Mac vs. Linux GPU difference without hand-waving.
- [ ] I have a CPU vs. Metal speed number to quote (`docs/metrics.md`).

## 9. On-prem vs. cloud API trade-offs

**Plain explanation**: Cloud LLM APIs give the best quality with no hardware to manage, but data leaves your network and cost grows per token. On-prem keeps data local and has near-zero marginal cost, but quality is limited by your hardware and you own the operations.

**In this repo**:
- ADR [0001](../decisions/0001-on-prem-rag-over-cloud-api.md).
- `docs/metrics.md`: development cost and model comparison.

**Interview questions**:
- Why build on-prem instead of calling a cloud API?
- When would you switch to a cloud API? What would you measure first?
- How would you handle 20 concurrent users on one Mac?
- You built it with a cloud coding assistant. Isn't that a contradiction? (No: only this repo and the sample project were used, never company code.)

**Self-check**:
- [ ] I can state the privacy, cost and quality trade-off in three sentences.
- [ ] I can name a hybrid option and its risks.

## 10. RAG evaluation methods

**Plain explanation**: "It looks right" is not evaluation. Build a fixed question set with expected answers and the files that should be cited, then score **retrieval** (were the right files retrieved?) separately from **generation** (is the answer correct and grounded?). Track latency too. Re-run the same set after every change to models, chunking or `top_k`.

**In this repo**:
- [`docs/evaluation/questions.md`](../evaluation/questions.md): 10 questions on the sample project, with expected answers, expected citations and scoring columns.
- `docs/metrics.md`: accuracy, citation accuracy and latency per model.
- `backend/tests/test_rag.py`: unit-level checks that citations and line numbers make it into the prompt.

**Interview questions**:
- How do you know your RAG system is good?
- What is the difference between retrieval metrics (recall@k, hit rate) and answer metrics (correctness, faithfulness)?
- How do you test that the system says "not found" instead of hallucinating?
- What would you automate next (e.g. an LLM-as-judge, CI regression)?

**Self-check**:
- [ ] I ran the 10-question set on at least two models and recorded the results.
- [ ] I can explain recall@k and faithfulness with an example from the sample project.

## 11. Timeouts across a proxy chain

**Plain explanation**: A request from the browser passes through several hops, and each hop gives up after its own timeout: browser → port forwarder (e.g. Codespaces) → nginx → backend → Ollama. The request can only wait as long as the **shortest** timeout in front of the slow part. A gateway that gives up returns **504 Gateway Timeout**. A good setup makes every timeout you own configurable, makes the innermost one fire first so its error message is specific, and shows progress in the UI.

**In this repo**:
- `frontend/nginx.conf.template`: `proxy_read_timeout ${PROXY_READ_TIMEOUT}s`, rendered by the nginx image's `envsubst` templates.
- `backend/app/config.py`: `llm_request_timeout`, `embed_request_timeout`. `backend/app/rag.py`: `OllamaTimeoutError`. `backend/app/main.py`: maps it to 504.
- `frontend/src/api.ts`: `ApiError` tells backend timeouts, proxy timeouts and dropped connections apart. `App.tsx`: "生成中" timer.
- ADR [0009](../decisions/0009-timeout-settings.md); [devlog 2026-11-01 Codespaces setup](../devlog/2026-11-01-codespace-setup.md).

**Interview questions**:
- What is the difference between 502 and 504?
- A query takes 2 minutes and nginx is set to 15 minutes, yet users get 504 after about 100 seconds. Where do you look?
- Why should the innermost timeout be the shortest one?
- How would you serve answers that take minutes through proxies you do not control? (Streaming, or an async job with polling.)

**Self-check**:
- [ ] I can draw the hops of a query in this repo and name the timeout setting of each.
- [ ] I can explain why raising `PROXY_READ_TIMEOUT` does not help when the 504 comes from a port forwarder.

## 12. Debugging long-running services from the shell

**Plain explanation**: A server runs until it is stopped, so in the foreground it "hangs" the terminal; run it with `&` (and `nohup`) and send its output to a log. `>` truncates a file and `>>` appends, so restarting with `>` can erase the evidence of the last good start. `curl -s` hides errors, while `curl -sS` stays quiet but still prints them. To test what a container can reach, run the test **from a container** (`docker run --rm curlimages/curl ...`), not from the host.

**In this repo**:
- `scripts/smoke-test.sh`: `curl -sS --fail-with-body` everywhere.
- `.github/workflows/ci.yml`: Ollama started with `nohup ... > ollama.log 2>&1 &`, and the log printed on failure.
- [devlog 2026-11-01 Codespaces setup](../devlog/2026-11-01-codespace-setup.md), Problems 1–4.

**Interview questions**:
- Your terminal "froze" after starting a server. What happened?
- How do you check whether something is already listening on a port?
- Why can `curl localhost:11434` work on the host but fail from a container?
- What does `2>&1` do, and why does its position matter?

**Self-check**:
- [ ] I can start a server in the background, find its PID and port, and stop it.
- [ ] I can prove container-to-host connectivity with one `docker run` command.

## 13. CI/CD and GitHub Actions

**Plain explanation**: **CI** (continuous integration) automatically builds and tests every change, so problems are found when they are cheap to fix. **CD** (continuous delivery/deployment) automates releasing it. In GitHub Actions, a **workflow** (`.github/workflows/*.yml`) is triggered by **events** (`push`, `pull_request`), and contains **jobs** that run in parallel on fresh **runners** unless linked with `needs`. Each job is a list of **steps** (shell commands or reusable **actions**). Caches (pip, Docker layers, models) keep repeat runs fast. A good pipeline runs cheap checks on every push and expensive end-to-end tests only where they matter.

**In this repo**:
- `.github/workflows/ci.yml`: `backend-tests`, `compose-config`, `docker-build` (matrix), and `e2e-smoke` (PRs into `main` only, `needs` the fast jobs).
- `docker-compose.ci.yml`: the CI-only override. `scripts/smoke-test.sh`: health → index → query → citation checks.
- ADR [0007](../decisions/0007-multi-environment-testing-strategy.md) (what each environment tests), ADR [0008](../decisions/0008-ci-design.md) (why several jobs, why the smallest model).
- The CI status badge at the top of the README.

**Interview questions**:
- What runs in your CI, and why is the end-to-end test separate from the unit tests?
- Why does the smoke test use a 0.5B model? What can it **not** tell you?
- How do you keep CI fast? (Parallel jobs, caching, `needs`, running slow jobs only on PRs.)
- An end-to-end job fails but passes on re-run. How do you tell a flaky test from a real bug?
- What would CD look like for an on-prem system on one Mac?

**Self-check**:
- [ ] I can explain workflow, job, step, runner, action and `needs` with this repo's file.
- [ ] I can read a failed run's logs (including the `docker compose logs` dump) and find the cause.
- [ ] I can explain the hard checks vs. the soft check in `scripts/smoke-test.sh`.

## 14. Server-Sent Events and streaming responses

**Plain explanation**: A normal HTTP response is sent when it is complete. A **streamed** response sends its body in pieces while it is still being produced. **Server-Sent Events (SSE)** is a simple text format for such a stream: `Content-Type: text/event-stream`, and frames like `event: token` / `data: {...}` separated by a blank line. It is one-way (server → client) over a plain HTTP response, unlike a **WebSocket**, which upgrades the connection to a two-way channel. For an LLM this gives two things: the user sees the answer as it is written (**time to first token** instead of total time), and the connection carries data the whole time, so proxies with idle limits do not cut it. A **heartbeat** is a small event sent when there is nothing else to send. Once a stream has started the status code is already 200, so later errors must be sent as events.

**In this repo**:
- `backend/app/rag.py`: `RagService.stream()` yields `sources` → `token`* → `done`.
- `backend/app/main.py`: `POST /query/stream`, `stream_answer()` (worker thread → `asyncio.Queue` → SSE frames, heartbeat when the queue is quiet, `error` event).
- `frontend/src/api.ts`: `queryStream()` reads the body with `fetch` + a stream reader and parses SSE frames. `App.tsx`: cited files first, then tokens, time to first token and total time, partial answer kept on error.
- `scripts/smoke-test.sh`: the streaming part checks event order and arrival times. ADR [0010](../decisions/0010-streaming-responses.md).

**Interview questions**:
- SSE or WebSocket for streaming LLM answers? Why?
- Why not use the browser's `EventSource` here?
- What do you send first, and why? (Sources: they are ready in seconds and the prompt needs them anyway.)
- The stream fails halfway. What status code does the client see, and how does it find out?
- What is time to first token, and why does it matter more than total time for perceived speed?

**Self-check**:
- [ ] I can write a valid SSE frame by hand and read a stream with `curl -N`.
- [ ] I can explain how the backend sends heartbeats while the model is silent.
- [ ] I can explain what the UI does when the connection drops mid-answer.

## 15. Reverse proxy buffering

**Plain explanation**: A reverse proxy such as nginx sits between the client and the application. By default nginx **buffers** responses from the upstream: it reads them into memory (or temp files) so the upstream is freed quickly even for a slow client. Compression (**gzip**) also has to collect data before it can emit a compressed block. Both are good for normal pages and bad for streams: the client may get nothing until a buffer fills or the response ends. For streaming endpoints you turn them off (`proxy_buffering off`, `gzip off`), or the application asks for it with the `X-Accel-Buffering: no` header. Timeouts change meaning too: `proxy_read_timeout` is the time **between two reads**, not for the whole response, so regular data keeps a long stream alive.

**In this repo**:
- `frontend/nginx.conf.template`: `location = /api/query/stream` with `proxy_buffering off`, `proxy_cache off`, `gzip off`; the normal `/api/` location keeps the defaults.
- `backend/app/main.py`: `X-Accel-Buffering: no`, `Cache-Control: no-cache` on the stream.
- `scripts/smoke-test.sh`: `curl --compressed` like a browser; fails with `STREAM_STRICT=1` if all events arrive in one burst. Local finding: nginx 1.29 still passed events through with `proxy_buffering on` alone, but gzip held the whole answer back (ADR [0010](../decisions/0010-streaming-responses.md)).

**Interview questions**:
- Why does nginx buffer upstream responses by default? What does that protect?
- Your SSE endpoint works with `curl` against the backend but arrives in one burst through nginx in the browser. What do you check?
- What does `proxy_read_timeout` measure for a streamed response?
- Which other layers can buffer a stream? (CDNs, corporate proxies, compression middleware, the client library.)

**Self-check**:
- [ ] I can show the difference between a buffered and an unbuffered stream with timestamps.
- [ ] I can explain why the smoke test sends `Accept-Encoding: gzip`.

## 16. Dev Containers and Codespaces

**Plain explanation**: A **dev container** is a development environment described in code (`.devcontainer/devcontainer.json`): a base image, **features** (Docker, Python, Node…), forwarded ports, environment variables, and **lifecycle commands**. **GitHub Codespaces** (and VS Code locally) builds a container from it. `postCreateCommand` runs once when the container is created; `postStartCommand` runs **every time** it starts. A stopped codespace keeps its files but loses its running processes, so servers have to be started in `postStartCommand`. `hostRequirements` asks for a minimum machine size. `portsAttributes` labels ports and controls auto-forwarding. **docker-in-docker** runs a separate Docker daemon inside the container.

**In this repo**:
- `.devcontainer/devcontainer.json`: 4 cores / 16 GB, docker-in-docker, `COMPOSE_FILE` and `OLLAMA_MODELS` in `containerEnv`, port 8080 labelled, 11434 / 6333 never forwarded.
- `.devcontainer/post-create.sh` (install Ollama, create `.env` from `.env.codespaces`) and `post-start.sh` (start Ollama on `0.0.0.0`, pull models, `docker compose up`, index if empty, doctor).
- `docker-compose.codespaces.yml` applied with `COMPOSE_FILE`; `scripts/doctor.sh`. ADR [0011](../decisions/0011-devcontainer-for-codespaces.md).

**Interview questions**:
- What is the difference between `postCreateCommand` and `postStartCommand`? Which one starts a server, and why?
- How do you apply a Compose override only in one environment without affecting the others?
- Why not run Ollama in Compose inside the codespace?
- How do you keep large downloads (models) across container rebuilds?
- Why should port 11434 never be forwarded or made public?

**Self-check**:
- [ ] I can explain each lifecycle command in this repo's `devcontainer.json` and when it runs.
- [ ] I can read `scripts/doctor.sh` output and fix the first failing check.

---

# 知識檢核清單

> 每個主題包含：淺白解釋、在本 repo 的程式碼位置、面試可能被問的問題、自我檢核。只有在**不看筆記**也講得出來時才打勾。

## 1. RAG（檢索增強生成）

**淺白解釋**：LLM 不認識你的程式碼。RAG 會先從你自己的資料中**檢索**出最相關的片段，貼進提示詞，再要求 LLM **只根據這些片段**回答。模型的工作從「記憶」變成「閱讀並解釋」。

**本 repo 對應位置**：
- `backend/app/rag.py`：`RagService.retrieve()` 把問題轉成向量並搜尋 Qdrant；`build_prompt()` 把片段編號成 `[1]…[n]`，並附上 `檔案:起始行-結束行`；`RagService.answer()` 呼叫 LLM。
- 同一個檔案的 `SYSTEM_PROMPT` 要求模型只根據片段回答，並且要引用。

**面試可能問**：
- 從使用者提問到得到回答，中間發生了什麼？
- 為什麼用 RAG，而不是用程式碼去微調模型？
- 怎麼減少 RAG 系統的幻覺？
- 檢索到的片段裡沒有答案時會怎樣？

**自我檢核**：
- [ ] 能憑記憶畫出索引階段與查詢階段的流程。
- [ ] 能解釋 RAG、微調、長上下文提示的差異。
- [ ] 能指出檢索到的片段是在哪一行放進提示詞的。

## 2. Embedding（向量化）

**淺白解釋**：embedding 模型把文字轉成一串數字（向量），讓意思相近的文字在空間中彼此靠近。「玩家在哪裡跳躍？」會落在 `Player.update` 程式碼附近。通常用餘弦相似度衡量有多接近。

**本 repo 對應位置**：
- `backend/app/indexer.py`：`embed_text()` 組出要向量化的文字（檔案路徑＋符號標頭＋程式碼）；`_index_file()` 分批向量化。
- `backend/app/config.py`：`query_prefix`／`doc_prefix`。nomic 的問題要加 `search_query:`，文件要加 `search_document:`。
- `backend/app/services.py`：`OllamaEmbedding` 設定；`EMBED_MODEL` 選擇模型。

**面試可能問**：
- 什麼是 embedding？餘弦相似度在衡量什麼？
- 為什麼查詢和文件必須用同一個 embedding 模型？
- 換了 embedding 模型卻沒有重新索引會怎樣？（本 repo 的 collection 名稱由模型名稱推導。）
- 為什麼有些模型的查詢和文件要加不同前綴？

**自我檢核**：
- [ ] 能用二維的例子解釋向量相似度。
- [ ] 知道 collection 名稱為什麼包含 embedding 模型名稱。
- [ ] 能說明「環境變數為空字串導致 nomic 前綴失效」的問題。

## 3. Chunking（切塊）

**淺白解釋**：文件太大，無法整份向量化或送進模型，所以要切成片段。片段太小會失去上下文，太大則讓語意變模糊並浪費提示詞空間。對程式碼來說，最好的切法是**依語法結構**：一個函式或一個 class 一塊。

**本 repo 對應位置**：
- `backend/app/chunker.py`：TS/JS 用 tree-sitter（`_chunk_js`、`_split_class`），Markdown 依標題（`_chunk_markdown`），其他用行數視窗（`_window_chunks`）。
- `backend/tests/test_chunker.py`：檢查行號是否正確與各種切分規則。
- ADR [0004](../decisions/0004-chunking-by-file-type.md)。

**面試可能問**：
- 片段大小怎麼決定？有哪些取捨？
- 為什麼依語法樹切，而不是固定大小？
- 怎麼確保引用的行號正確？
- 遇到 500 行的 class 怎麼處理？

**自我檢核**：
- [ ] 能解釋什麼是 tree-sitter，以及為什麼它比正規表示式好。
- [ ] 能說明 JSDoc、import 與過大的 class 會被怎麼處理。
- [ ] 知道檔案雜湊值為什麼要包含 `CHUNK_MAX_CHARS`。

## 4. 向量資料庫

**淺白解釋**：向量資料庫儲存向量與 metadata，能快速找出最接近查詢向量的資料，通常使用 HNSW 這類近似索引。metadata 篩選（例如 `file_path == X`）可以只搜尋或刪除其中一部分資料。

**本 repo 對應位置**：
- `backend/app/store.py`：`CodeVectorStore`。`query()` 做相似度搜尋；`file_hashes()` 掃描 payload 供增量索引使用；`delete_file()` 依條件刪除；`_store()` 處理 wrapper 只在建構時偵測格式的問題。
- `docker-compose.yml`：Qdrant 服務與 `qdrant_data` volume。
- ADR [0003](../decisions/0003-qdrant-vector-database.md)。

**面試可能問**：
- 為什麼用向量資料庫，而不是把向量存在 Postgres 或 NumPy 陣列？
- 什麼是近似最近鄰搜尋（如 HNSW）？「近似」要付出什麼代價？
- 這裡的增量索引怎麼運作？以什麼為準？
- 說一個你在向量資料庫上遇到的問題，以及怎麼找到原因。

**自我檢核**：
- [ ] 能各用一句話比較 Qdrant、Chroma、pgvector、FAISS。
- [ ] 能解釋 `text-dense` 問題，以及單元測試為什麼沒抓到。
- [ ] 能解釋 payload index，以及為什麼要為 `file_path` 建立。

## 5. 模型量化

**淺白解釋**：模型權重通常是 16 位元的數字。量化是用更少的位元（例如 4 位元）來儲存，記憶體大約減為四分之一、推論也更快，代價是品質稍微下降。Ollama 預設的標籤（例如 `Q4_K_M`）就是 4 位元量化。

**本 repo 對應位置**：
- `.env.example`：`LLM_MODEL`。`qwen2.5-coder:14b` 這個標籤約 9GB，因為它是 Q4。
- ADR [0005](../decisions/0005-model-selection-and-hardware.md)：大小對照表。

**面試可能問**：
- 14B 模型在 FP16 和 Q4 下大約各需要多少記憶體？
- 量化會造成什麼品質損失？什麼情況下影響比較大？
- `Q4_K_M`、`Q8_0` 這類名稱大致代表什麼？

**自我檢核**：
- [ ] 能估算模型記憶體：參數量 × 位元數 ÷ 8（＋開銷）。
- [ ] 能解釋為什麼 Q4 是地端推論常見的平衡點。

## 6. 模型大小與硬體

**淺白解釋**：模型需要的記憶體是**權重＋KV cache＋開銷**，其中 KV cache 會隨上下文長度增加。生成速度主要取決於記憶體頻寬。Apple Silicon 的 GPU 與 CPU 共用統一記憶體，但 macOS 預設只讓 GPU 使用其中一部分。

**本 repo 對應位置**：
- `backend/app/services.py`：`context_window=settings.llm_num_ctx` 會以 `num_ctx` 傳給 Ollama。
- `.env.example`：`LLM_NUM_CTX`、`OLLAMA_KEEP_ALIVE`。
- ADR [0005](../decisions/0005-model-selection-and-hardware.md)；`docs/metrics.md` 的模型比較表。

**面試可能問**：
- 為什麼 32GB 的 Mac 選 14B，而不是 32B？
- 什麼是 KV cache？為什麼很長的 RAG 提示詞需要更多記憶體？
- 筆電上每秒能產生多少 token，受什麼限制？
- `num_ctx` 太小會怎樣？（檢索到的程式碼會被默默截斷。）

**自我檢核**：
- [ ] 能在白板上估算 3B／14B／32B 的記憶體需求。
- [ ] 已經用 `ollama ps` 量過實際記憶體，並記錄到 metrics。

## 7. Docker 網路（`host.docker.internal`／`host-gateway`）

**淺白解釋**：在容器裡，`localhost` 指的是容器自己，而不是你的電腦。要連到主機上的服務，Docker Desktop 提供了 `host.docker.internal` 這個名稱。在 Linux 上要自己用 `extra_hosts: host.docker.internal:host-gateway` 加上，而且主機上的服務必須監聽容器連得到的網卡（`0.0.0.0`，而不是 `127.0.0.1`）。

**本 repo 對應位置**：
- `docker-compose.yml`：後端的 `extra_hosts`；`OLLAMA_BASE_URL=http://host.docker.internal:11434`。
- `frontend/nginx.conf.template`：`proxy_pass http://backend:8000/` 使用 Compose 的服務名稱 DNS。
- [devlog 2026-11-01](../devlog/2026-11-01.md)；ADR [0006](../decisions/0006-multi-environment-deployment.md)。

**面試可能問**：
- 為什麼後端容器不能呼叫 `http://localhost:11434`？
- 同一個 Compose 專案的容器怎麼找到彼此？
- 為什麼 Codespaces 需要 `OLLAMA_HOST=0.0.0.0`，Mac 卻不用？
- 綁定 `0.0.0.0` 有什麼資安影響？

**自我檢核**：
- [ ] 能在一分鐘內解釋網路命名空間與 loopback。
- [ ] 能一步步排查容器裡的「connection refused」。

## 8. Apple Silicon 與 Docker 的 GPU 限制

**淺白解釋**：Mac 上的 Docker 是在 Linux VM 裡執行容器，而 Apple 的 Metal GPU 不會開放給這台 VM。所以 LLM 推論這類吃 GPU 的工作，應該直接在 macOS 上執行。Linux 搭配 NVIDIA GPU 時，容器可以透過 NVIDIA Container Toolkit 使用 GPU，情況不一樣。

**本 repo 對應位置**：
- Compose 刻意不包含 Ollama 服務；`scripts/setup.sh` 會在主機上檢查並啟動 Ollama。
- ADR [0002](../decisions/0002-ollama-outside-docker-on-mac.md)；README 的「為什麼 Ollama 不放在 Docker 裡」。

**面試可能問**：
- 為什麼你的 docker-compose 裡沒有 Ollama？
- 換成有 NVIDIA GPU 的 Linux 伺服器時會有什麼不同？
- 什麼是統一記憶體？它對地端 LLM 有什麼影響？

**自我檢核**：
- [ ] 能清楚說明 Mac 和 Linux 在 GPU 上的差異，不含糊帶過。
- [ ] 有 CPU 和 Metal 的速度比較數據可以引用（`docs/metrics.md`）。

## 9. 地端與雲端 API 的取捨

**淺白解釋**：雲端 LLM API 品質最好、也不用管硬體，但資料會離開公司網路，費用按 token 增加。地端讓資料留在本機、邊際成本接近零，但品質受限於硬體，維運也要自己負責。

**本 repo 對應位置**：
- ADR [0001](../decisions/0001-on-prem-rag-over-cloud-api.md)。
- `docs/metrics.md`：開發成本與模型比較。

**面試可能問**：
- 為什麼要做地端，而不是呼叫雲端 API？
- 什麼情況下會改用雲端 API？會先量測什麼？
- 一台 Mac 要怎麼應付 20 個人同時使用？
- 你是用雲端程式助手建出這套系統的，這不是矛盾嗎？（不是：過程只用到本 repo 與範例專案，從未用到公司程式碼。）

**自我檢核**：
- [ ] 能用三句話說明隱私、成本、品質的取捨。
- [ ] 能提出一個混合方案，並說明它的風險。

## 10. RAG 評估方法

**淺白解釋**：「看起來是對的」不叫評估。要建立固定的題組，附上預期答案和應該引用的檔案，然後把**檢索**（有沒有找到正確的檔案？）和**生成**（回答是否正確、是否有根據？）分開評分，並記錄回應時間。每次更換模型、切塊方式或 `top_k` 之後，都用同一組題目重跑。

**本 repo 對應位置**：
- [`docs/evaluation/questions.md`](../evaluation/questions.md)：10 題範例專案的評估問題，附預期答案、應引用的檔案與評分欄。
- `docs/metrics.md`：各模型的答對率、引用正確率與回應時間。
- `backend/tests/test_rag.py`：在單元測試層級確認引用與行號有放進提示詞。

**面試可能問**：
- 你怎麼知道你的 RAG 系統好不好？
- 檢索指標（recall@k、命中率）和回答指標（正確性、忠實度）有什麼不同？
- 怎麼測試系統會回答「找不到」，而不是編造答案？
- 接下來會自動化哪些部分（例如 LLM-as-judge、CI 回歸測試）？

**自我檢核**：
- [ ] 至少用兩個模型跑過 10 題評估，並記錄結果。
- [ ] 能用範例專案的例子解釋 recall@k 和忠實度。

## 11. 代理鏈上的逾時

**淺白解釋**：瀏覽器送出的請求會經過好幾段連線，每一段都會在自己的逾時時間到了就放棄：瀏覽器 → 連接埠轉發（例如 Codespaces） → nginx → 後端 → Ollama。請求最多只能等到慢的那一段前面**最短**的那個逾時。負責轉送的閘道放棄時，會回傳 **504 Gateway Timeout**。好的做法是：自己能控制的逾時都可以設定、最內層的逾時最先觸發（錯誤訊息才會具體），並在介面上顯示進度。

**本 repo 對應位置**：
- `frontend/nginx.conf.template`：`proxy_read_timeout ${PROXY_READ_TIMEOUT}s`，由 nginx 映像檔的 `envsubst` template 機制產生設定。
- `backend/app/config.py`：`llm_request_timeout`、`embed_request_timeout`。`backend/app/rag.py`：`OllamaTimeoutError`。`backend/app/main.py`：轉成 504。
- `frontend/src/api.ts`：`ApiError` 區分後端逾時、代理逾時與連線中斷。`App.tsx`：「生成中」計時。
- ADR [0009](../decisions/0009-timeout-settings.md)；[devlog 2026-11-01 Codespaces 環境建置](../devlog/2026-11-01-codespace-setup.md)。

**面試可能問**：
- 502 和 504 差在哪裡？
- 一次查詢要 2 分鐘，nginx 設了 15 分鐘，使用者卻在約 100 秒後收到 504。你會從哪裡查起？
- 為什麼最內層的逾時應該最短？
- 要透過你無法控制的代理，提供需要好幾分鐘才能產生的回答，你會怎麼做？（串流，或非同步工作加輪詢。）

**自我檢核**：
- [ ] 能畫出本 repo 一次查詢經過的連線段，並說出每一段的逾時設定。
- [ ] 能解釋為什麼 504 來自連接埠轉發時，調高 `PROXY_READ_TIMEOUT` 也沒用。

## 12. 在 shell 裡排查常駐服務

**淺白解釋**：伺服器會一直執行到被停止為止，所以在前景執行時會讓終端機看起來「卡住」；要用 `&`（加上 `nohup`）放到背景，並把輸出寫進 log。`>` 會清空檔案，`>>` 是附加，所以用 `>` 重新啟動，可能會把上一次成功啟動的證據蓋掉。`curl -s` 會隱藏錯誤，`curl -sS` 安靜但照樣印出錯誤。要測試容器連得到什麼，就要**從容器裡**測試（`docker run --rm curlimages/curl ...`），而不是從主機。

**本 repo 對應位置**：
- `scripts/smoke-test.sh`：一律使用 `curl -sS --fail-with-body`。
- `.github/workflows/ci.yml`：以 `nohup ... > ollama.log 2>&1 &` 啟動 Ollama，失敗時印出 log。
- [devlog 2026-11-01 Codespaces 環境建置](../devlog/2026-11-01-codespace-setup.md) 的問題 1～4。

**面試可能問**：
- 啟動伺服器後終端機「卡住」了，發生了什麼事？
- 怎麼確認某個連接埠是不是已經有程式在監聽？
- 為什麼 `curl localhost:11434` 在主機上通，從容器裡卻不通？
- `2>&1` 是什麼意思？為什麼它的位置很重要？

**自我檢核**：
- [ ] 能把伺服器放到背景執行、找出它的 PID 與連接埠，並停止它。
- [ ] 能用一行 `docker run` 指令證明容器連得到主機。

## 13. CI/CD 與 GitHub Actions

**淺白解釋**：**CI**（持續整合）會自動 build 並測試每一次變更，讓問題在修正成本還低的時候就被發現。**CD**（持續交付／部署）則是把發佈也自動化。在 GitHub Actions 裡，**workflow**（`.github/workflows/*.yml`）由**事件**（`push`、`pull_request`）觸發，裡面有多個 **job**；除非用 `needs` 串起來，否則 job 會在各自全新的 **runner** 上平行執行。每個 job 由一連串 **step** 組成（shell 指令，或可重複使用的 **action**）。快取（pip、Docker layer、模型）讓重複執行變快。好的流程是：便宜的檢查每次 push 都跑，昂貴的端到端測試只在真正需要的地方跑。

**本 repo 對應位置**：
- `.github/workflows/ci.yml`：`backend-tests`、`compose-config`、`docker-build`（matrix），以及 `e2e-smoke`（只在對 `main` 的 PR 執行，用 `needs` 等快速的 job 通過）。
- `docker-compose.ci.yml`：CI 專用的 override。`scripts/smoke-test.sh`：健康檢查 → 索引 → 查詢 → 檢查引用。
- ADR [0007](../decisions/0007-multi-environment-testing-strategy.md)（每個環境測什麼）、ADR [0008](../decisions/0008-ci-design.md)（為什麼拆成多個 job、為什麼用最小模型）。
- README 最上方的 CI 狀態徽章。

**面試可能問**：
- 你的 CI 跑了哪些東西？為什麼端到端測試要和單元測試分開？
- 為什麼冒煙測試用 0.5B 模型？它**無法**告訴你什麼？
- 怎麼讓 CI 保持快速？（平行 job、快取、`needs`、慢的 job 只在 PR 跑。）
- 端到端 job 失敗了，重跑卻通過。你怎麼分辨是不穩定的測試，還是真的有 bug？
- 只在一台 Mac 上執行的地端系統，CD 會長什麼樣子？

**自我檢核**：
- [ ] 能用本 repo 的 workflow 檔解釋 workflow、job、step、runner、action 與 `needs`。
- [ ] 能讀懂失敗執行的 log（包括 `docker compose logs` 的輸出），找出原因。
- [ ] 能解釋 `scripts/smoke-test.sh` 裡硬性檢查與軟性檢查的差別。

## 14. Server-Sent Events 與串流回應

**淺白解釋**：一般的 HTTP 回應要等內容完整才送出。**串流**回應則是一邊產生、一邊分段送出內容。**Server-Sent Events（SSE）**是一種簡單的串流文字格式：`Content-Type: text/event-stream`，每個事件寫成 `event: token`／`data: {...}`，以空行分隔。它是在一般 HTTP 回應上的單向傳輸（伺服器 → 用戶端），不像 **WebSocket** 會把連線升級成雙向通道。對 LLM 來說有兩個好處：使用者看著回答逐字出現（在意的是**首字延遲**而不是總時間），而且連線上一直有資料，有閒置上限的代理就不會切斷它。**Heartbeat** 是沒有其他東西可送時送出的小事件。串流一旦開始，狀態碼就已經是 200，之後的錯誤只能用事件傳送。

**本 repo 對應位置**：
- `backend/app/rag.py`：`RagService.stream()` 依序產生 `sources` → `token`* → `done`。
- `backend/app/main.py`：`POST /query/stream`、`stream_answer()`（背景執行緒 → `asyncio.Queue` → SSE 事件，佇列沒動靜時送 heartbeat，失敗時送 `error` 事件）。
- `frontend/src/api.ts`：`queryStream()` 用 `fetch` 加串流讀取器讀取 body 並解析 SSE。`App.tsx`：先顯示引用的檔案，再逐字顯示，顯示首字延遲與總耗時，出錯時保留已收到的內容。
- `scripts/smoke-test.sh`：串流部分檢查事件順序與到達時間。ADR [0010](../decisions/0010-streaming-responses.md)。

**面試可能問**：
- 串流 LLM 回答要用 SSE 還是 WebSocket？為什麼？
- 為什麼這裡不用瀏覽器的 `EventSource`？
- 第一個送出的是什麼？為什麼？（引用片段：幾秒內就準備好，而且組提示詞本來就需要。）
- 串流到一半失敗了，用戶端看到的狀態碼是什麼？它怎麼知道出錯？
- 什麼是首字延遲？為什麼它比總時間更影響「感覺上的速度」？

**自我檢核**：
- [ ] 能手寫一個正確的 SSE 事件，並用 `curl -N` 讀取串流。
- [ ] 能解釋模型沉默時，後端怎麼送出 heartbeat。
- [ ] 能說明回答到一半連線中斷時，介面會怎麼處理。

## 15. 反向代理的緩衝

**淺白解釋**：nginx 這類反向代理位於用戶端與應用程式之間。nginx 預設會**緩衝**上游的回應：先讀進記憶體（或暫存檔），即使用戶端很慢，上游也能盡快被釋放。壓縮（**gzip**）也必須先收集一批資料，才能產生壓縮區塊。這兩者對一般網頁有好處，對串流卻有害：用戶端可能要等緩衝區滿了、或回應結束，才收到任何東西。串流端點要把它們關掉（`proxy_buffering off`、`gzip off`），或由應用程式送出 `X-Accel-Buffering: no` 標頭要求關閉。逾時的意義也會改變：`proxy_read_timeout` 是**兩次讀取之間**的時間，不是整個回應的時間，所以只要定期有資料，長時間的串流就不會被切斷。

**本 repo 對應位置**：
- `frontend/nginx.conf.template`：`location = /api/query/stream` 設定 `proxy_buffering off`、`proxy_cache off`、`gzip off`；一般的 `/api/` 維持預設。
- `backend/app/main.py`：串流回應帶有 `X-Accel-Buffering: no`、`Cache-Control: no-cache`。
- `scripts/smoke-test.sh`：像瀏覽器一樣用 `curl --compressed`；設定 `STREAM_STRICT=1` 時，所有事件同時到達就判定失敗。本機測試的發現：只開 `proxy_buffering on` 時，nginx 1.29 仍會逐一轉送事件，但 gzip 會把整個回答壓到最後才送（ADR [0010](../decisions/0010-streaming-responses.md)）。

**面試可能問**：
- nginx 為什麼預設會緩衝上游回應？它保護的是什麼？
- 你的 SSE 端點直接用 `curl` 打後端正常，透過 nginx 在瀏覽器裡卻一次全部出現。你會檢查什麼？
- 對串流回應來說，`proxy_read_timeout` 量的是什麼？
- 還有哪些層可能緩衝串流？（CDN、公司代理、壓縮 middleware、用戶端函式庫。）

**自我檢核**：
- [ ] 能用時間戳記示範有緩衝與沒有緩衝的串流差在哪裡。
- [ ] 能解釋冒煙測試為什麼要送出 `Accept-Encoding: gzip`。

## 16. Dev Containers 與 Codespaces

**淺白解釋**：**dev container** 是用程式碼描述的開發環境（`.devcontainer/devcontainer.json`）：基底映像、**feature**（Docker、Python、Node…）、轉發的連接埠、環境變數，以及**生命週期指令**。**GitHub Codespaces**（或本機的 VS Code）會依它建立容器。`postCreateCommand` 在容器建立時執行一次；`postStartCommand` 則是**每次**啟動都會執行。停止的 codespace 會保留檔案，但執行中的程序會消失，所以伺服器要在 `postStartCommand` 裡啟動。`hostRequirements` 指定最低機型規格。`portsAttributes` 為連接埠加上標籤並控制自動轉發。**docker-in-docker** 會在容器裡另外執行一個 Docker daemon。

**本 repo 對應位置**：
- `.devcontainer/devcontainer.json`：4 核心／16GB、docker-in-docker、`containerEnv` 裡的 `COMPOSE_FILE` 與 `OLLAMA_MODELS`、8080 埠的標籤，11434／6333 永遠不轉發。
- `.devcontainer/post-create.sh`（安裝 Ollama、從 `.env.codespaces` 建立 `.env`）與 `post-start.sh`（以 `0.0.0.0` 啟動 Ollama、拉模型、`docker compose up`、沒有索引時建立索引、執行 doctor）。
- 透過 `COMPOSE_FILE` 套用的 `docker-compose.codespaces.yml`；`scripts/doctor.sh`。ADR [0011](../decisions/0011-devcontainer-for-codespaces.md)。

**面試可能問**：
- `postCreateCommand` 和 `postStartCommand` 差在哪裡？伺服器要在哪一個啟動？為什麼？
- 怎麼讓 Compose override 只在某個環境生效，而不影響其他環境？
- 為什麼不在 codespace 裡把 Ollama 放進 Compose？
- 怎麼讓大型下載（模型）在重建容器後仍然保留？
- 為什麼 11434 埠絕對不能轉發或設為公開？

**自我檢核**：
- [ ] 能解釋本 repo `devcontainer.json` 裡每個生命週期指令的作用與執行時機。
- [ ] 能讀懂 `scripts/doctor.sh` 的輸出，並修正第一個失敗的項目。
