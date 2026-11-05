# Deploying a local LLM: narrowing down failures one layer at a time

> **Status**: draft, not published. `[Screenshot: …]` marks where a screenshot should go; `{待填}` marks numbers not measured yet.
> **Language**: English version. The Traditional Chinese version is [`03-local-llm-deployment-pitfalls.zh-TW.md`](03-local-llm-deployment-pitfalls.zh-TW.md). The two match section by section; update both together.
> **Plan**: Article 3 in [`../article-series.md`](../article-series.md). Sources: [devlog 2026-11-01](../../devlog/2026-11-01.md), [devlog 2026-11-01 Codespaces setup](../../devlog/2026-11-01-codespace-setup.md), [devlog 2026-11-02](../../devlog/2026-11-02.md), [devlog 2026-11-03](../../devlog/2026-11-03.md), [`metrics.md`](../../metrics.md), ADRs [0002](../../decisions/0002-ollama-outside-docker-on-mac.md), [0006](../../decisions/0006-multi-environment-deployment.md), [0007](../../decisions/0007-multi-environment-testing-strategy.md), [0008](../../decisions/0008-ci-design.md), [0009](../../decisions/0009-timeout-settings.md), [0010](../../decisions/0010-streaming-responses.md), [0011](../../decisions/0011-devcontainer-for-codespaces.md).
> **Privacy**: every path, symbol and question comes from `examples/sample-game-frontend/` or this repo.

## TL;DR

- I built an on-prem codebase RAG system: Ollama runs on the host; Qdrant, a FastAPI + LlamaIndex backend and a React UI run in Docker.
- I had no Mac to test on, so I tested in GitHub Codespaces first (Linux, CPU only). I hit three problems. None was a logic bug. All three came from the **environment and the network**, and passing unit tests could not catch them.
- I debugged all three the same way: **test from where the caller sits, one hop at a time**, ruling out one layer per step.
- On CPU with a 3B model, one non-streaming query from inside the codespace (`curl` through nginx) took 54.7 seconds (`top_k` 4). The final 504 came from the Codespaces port forwarder cutting the connection at about 100 seconds. Raising our own timeouts did nothing; after switching to a streamed response the same kind of query completed from the browser through the forwarded URL (time to first token 30.4 s, total 43.8 s, 129 tokens). That run was only 43.8 seconds, so **a query longer than 100 seconds is still untested**.
- Bonus: a fourth problem was not in the services at all: `git push` was blocked by a Git LFS hook (see "Bonus").

---

## 1. Background: why build this, and why test in Codespaces

### Why an on-prem codebase RAG

In a game front-end project (roughly 50–300 files), the questions newcomers ask most are "where is X configured?" and "where does this flow start?". grep finds strings, but it cannot answer "why" or "how do these connect".

A cloud AI assistant can answer those questions, but two things ruled it out for me:

1. **The code cannot leave the company's machines.** This is a hard constraint.
2. **The team needs a shared tool**, not one subscription and one setup per person.

So the goal: run the whole pipeline on one machine, ask questions in natural language, and get answers that cite `file:start-end` line ranges, with neither code nor questions leaving the machine (ADR 0001).

Using the sample project as an example: for "Where is the invincibility time after the player gets hit configured?", a good answer points to `INVINCIBLE_MS = 1500` in `src/config/gameConfig.ts`, and to where `src/entities/Player.ts` uses it.

[Screenshot: the UI answering "Where is the invincibility time after the player gets hit configured?" with the gameConfig.ts citation expanded]

### Why Codespaces

The production machine is a Mac M2 with 32 GB, but **I had no Mac available** during development. Rather than wait, I ran the full pipeline in a free, disposable Linux environment:

- Install → index the sample project → ask from the UI → get an answer with citations.
- I swapped the 14B model for `qwen2.5-coder:3b`, because 14B is too slow on CPU for checking that the pipeline works. The embedding model stayed `nomic-embed-text`.

In hindsight, the value was not "getting it running sooner". Codespaces is **very different from a Mac**, and that surfaced a set of problems I would never see on the Mac but would certainly hit when deploying to a Linux server.

---

## 2. Architecture and how the three environments differ

```text
Browser ──► nginx (frontend container, /api proxy) ──► FastAPI + LlamaIndex (backend container) ──► Ollama (host)
                                                              │
                                                              └──► Qdrant (container)
```

One key decision: **Ollama does not go in Docker** (ADR 0002). Docker Desktop on macOS runs containers inside a Linux VM, and Apple's Metal GPU is not passed through to that VM. Put Ollama in compose and, on a Mac, it runs on CPU only. So Ollama always runs natively on the host, and containers call it at `http://host.docker.internal:11434`.

That is the natural choice on a Mac. On Linux, it is where things started to break. How the three environments differ (ADR 0006):

| Item | Mac M2 32 GB | GitHub Codespaces | EC2 GPU instance (under evaluation) |
| --- | --- | --- | --- |
| Purpose | Team production use | Linux rehearsal before deployment; pipeline check | Testing larger models such as 32B |
| Docker | Docker Desktop (Linux VM) | Linux, Docker Engine (docker-in-docker) | Linux, Docker Engine |
| GPU | Metal (host only) | None | NVIDIA (e.g. A10G 24 GB on `g5.xlarge`) |
| `host.docker.internal` | Provided by Docker Desktop | **Does not exist**; needs `extra_hosts: host-gateway` | **Does not exist**; same as Codespaces |
| Ollama listen address | Default `127.0.0.1` works | Must be `0.0.0.0` | Must be `0.0.0.0` (systemd override) |
| How Ollama starts | App / `brew services`, starts at login | `postStartCommand` on every start | systemd |
| `LLM_MODEL` | `qwen2.5-coder:14b` | `qwen2.5-coder:3b` | `qwen2.5-coder:32b` |
| Exposure | Frontend bound to `127.0.0.1`; open to the LAN only when needed | 11434 not forwarded; ports stay private | Security group allows SSH only; everything else via SSH tunnel |
| Tested | {待填} | Yes (this article) | {待填} |

The rule: **every environment uses the same `docker-compose.yml`**. Differences live only in `.env` and in how Ollama is started. `extra_hosts: host.docker.internal:host-gateway` is in the base file; it is harmless on Docker Desktop and required on Linux.

---

## 3. The pitfalls

### Pitfall 1: containers cannot reach Ollama

**Symptom**

All services were up, but the backend's `/health` said it could not reach Ollama. The odd part: in the codespace terminal,

```bash
curl -sS http://localhost:11434/api/version
```

worked.

```text
{待填: the ollama.error from /health, or the error in docker compose logs backend}
```

[Screenshot: /health reporting that Ollama is unreachable]

**Hypothesis**

"I can reach it from here" and "the container can reach it" are two different claims. Inside a container, `localhost` is the container itself. To reach the host, a container goes through the Docker bridge gateway, not the host's loopback. That left two suspect layers:

1. Name resolution: does `host.docker.internal` resolve on Linux?
2. Listen address: is Ollama listening on the bridge gateway interface?

**Verification**

Don't test from the host; **test from where the caller sits**. A throwaway container sees the same network as the backend container:

```bash
docker run --rm --add-host=host.docker.internal:host-gateway curlimages/curl -sS http://host.docker.internal:11434/api/version
```

This one line separates the two layers. `--add-host=…:host-gateway` mirrors `extra_hosts` in compose and takes care of name resolution. If it still says connection refused after that, the only remaining suspect is the listen address.

Next, check where Ollama is actually listening:

```bash
ss -ltnp | grep 11434
```

The default is `127.0.0.1:11434`, which only accepts connections from the same network namespace. Connections arriving through the bridge gateway are refused.

[Screenshot: ss -ltnp showing Ollama on 127.0.0.1:11434]

A smaller trap along the way: I started with `curl -s`, and on failure it printed nothing, so I could not tell a refused connection from a timeout or an empty response. `-s` turns off the progress bar **and** the error messages. Since then I always use `-sS` (`--show-error`).

**Fix**

```bash
OLLAMA_HOST=0.0.0.0 ollama serve
```

Plus, in compose:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

Why isn't this needed on a Mac? Docker Desktop resolves `host.docker.internal` by itself and forwards the connection to the host's loopback, so Ollama's default `127.0.0.1` works. Same config, and this error simply never shows up on a Mac.

**Security note**: `0.0.0.0` opens 11434 on every interface, and Ollama has no authentication. In Codespaces, keep 11434 private (the dev container now marks it as never forwarded). On EC2, block it with the security group.

[Screenshot: /health showing "status": "ok" after the fix]

---

### Pitfall 2: after restarting the codespace, indexing fails for every file

**Symptom**

The pipeline worked the day before. The next day I restarted the stopped codespace, ran indexing, and every file failed.

```text
{待填: the error message from the failed indexing run}
```

**Hypothesis**

The code, `.env` and model files were all still there. The only difference from the day before was that the codespace had been stopped and started. Indexing calls Ollama for embeddings, so Ollama was the first suspect.

**Verification**

Same method as Pitfall 1, from the inside out:

```bash
curl -sS http://localhost:11434/api/version
```

No connection. Check the process:

```bash
ss -ltnp | grep 11434
```

Nothing was listening on 11434. Ollama was not running at all.

The cause is simple: **a stopped codespace keeps its files but not its running processes**. The day before, I had started Ollama by hand in the background with `nohup ollama serve &`; after the restart it was gone. On a Mac, the Ollama app starts at login, so this is another problem you never see there.

**Fix**

Turn the manual steps into dev container configuration (ADR 0011). The key is the difference between two hooks:

- `postCreateCommand` runs **once, at creation**. Good for installing Ollama and creating `.env`.
- `postStartCommand` runs **on every start**. Long-running services belong here.

On every start, `.devcontainer/post-start.sh`:

1. Starts Ollama in the background with `OLLAMA_HOST=0.0.0.0` if it is not answering, appending to the log with `>>` (`>` wipes the previous log, which is another trap I hit).
2. Waits for Ollama, then pulls any missing models.
3. Runs `docker compose up -d`.
4. Indexes the sample project if Qdrant has no index yet.
5. Runs `scripts/doctor.sh` as a health check and prints the URL.

`devcontainer.json` also hard-codes the network decisions: `hostRequirements` asks for 4 CPUs / 16 GB / 32 GB; only port 8080 (the frontend) is forwarded, while 11434 (Ollama) and 6333 (Qdrant) are set to `ignore` and are never forwarded, so the security note from Pitfall 1 no longer depends on anyone remembering it. `postCreateCommand` creates `.env` from `.env.codespaces` (`qwen2.5-coder:3b`, `TOP_K=4`, `LLM_NUM_CTX=8192`).

Result: after rebuilding (or recreating) the codespace, `scripts/doctor.sh` passed 11 of 11 checks and I asked the first questions from the browser without typing a command (devlog 2026-11-02). Time from creating the codespace until the UI can answer: {待填}. **Whether Ollama and the stack come back after stopping and starting the codespace has not been tested yet** (an open item in devlog 2026-11-02), so "Pitfall 2 is solved" currently rests on the design, not on a test.

`scripts/doctor.sh` is the troubleshooting from these two pitfalls written down as a script: Ollama installed → process running → API answering → listen address → models → Docker → containers → **containers can reach Ollama** → backend `/health` → nginx proxy → Qdrant has an index (check 12, a Git LFS check, was added later; see "Bonus"). Each failed check prints the fix, and checks that depend on it are skipped, so it tells you directly which layer is broken.

[Screenshot: scripts/doctor.sh output with every check passing]

[Screenshot: docker compose ps, all healthy]

---

### Pitfall 3: tracking down a 504

This one took the longest, and it shows best what "narrowing down one layer at a time" means.

A query passes through several hops, and **each hop has its own timeout**:

```text
Browser → Codespaces port forwarder → nginx (/api) → backend (FastAPI) → Ollama
          not under our control         proxy_read_timeout  LLM_REQUEST_TIMEOUT
```

How long a request can wait is decided by **the least patient hop**.

#### Round 1: check every hop we control

**Symptom**: I asked a question in the UI; after a while it showed 504 Gateway Timeout.

```text
{待填: the error message shown in the UI}
```

[Screenshot: the UI showing 504 Gateway Timeout]

**Hypothesis**: a 504 comes from a proxy and the nearest proxy is nginx, so first suspect that one of our own timeouts was too short. A 3B model on CPU takes an estimated 1.5–2 minutes per query (`top_k=8`; an estimate, not a mean over 10 queries), which would exceed any short default.

**Verification**: list the actual setting of every hop (ADR 0009):

| Hop | Setting before the change | Problem |
| --- | --- | --- |
| nginx `proxy_read_timeout` / `proxy_send_timeout` | Hard-coded 900 s | Could not be changed without rebuilding the image |
| Backend → Ollama generation (`LLM_REQUEST_TIMEOUT`) | 600 s | A timeout came back as a generic 502 with a raw exception name |
| Backend → Ollama embeddings | **No timeout** (the ollama client waits forever by default) | A stuck call hangs the request until some other hop gives up |
| UI | One static "may take 30 s or more" | No sign of how long it had waited; on failure only `504 Gateway Timeout` |

nginx was at 900 seconds and the LLM at 600, while the 504 appeared after about 1.5–2 minutes, so neither could be the hop that gave up. The hypothesis died during verification, which left whatever sits **in front of** nginx.

**The fix I made anyway**: the table itself shows three gaps (hard-coded, no timeout, unclear message), so I made every timeout configurable in `.env`, defaulting to 300 seconds (ADR 0009):

| Variable | Hop | Default |
| --- | --- | --- |
| `PROXY_READ_TIMEOUT`, `PROXY_SEND_TIMEOUT` | nginx → backend | 300 |
| `LLM_REQUEST_TIMEOUT` | backend → Ollama (generation) | 300 |
| `EMBED_REQUEST_TIMEOUT` | backend → Ollama (embeddings; previously **no timeout at all**) | 300 |

300 seconds is about 2–3 times the estimated query time (1.5–2 minutes). nginx reads these through the official image's template mechanism (`/etc/nginx/templates/*.template` + `envsubst`), so after editing `.env`, `docker compose up -d` applies them without a rebuild.

Two more things got fixed along the way: on an Ollama timeout the backend now returns 504 naming the stage and the variable to change (it used to be a generic 502), and the UI shows "generating" plus seconds waited.

**Result**: this round of fixes did not make the 504 go away. The cut-off was at **about 100 seconds**, which matched none of 300, 600 or 900.

#### Round 2: cut at 100 seconds, so it is none of our settings

This was the turning point. Our timeouts were 300 seconds (900 and 600 before the change); none was 100. When the cut-off time does not match any of your own settings, **some other hop is giving up**.

Only one hop sits in front of nginx: **the Codespaces port forwarder**. The `https://<codespace>-8080.app.github.dev` URL you open in the browser does not connect straight to nginx. GitHub's forwarding proxy sits in between, with its own limit that we cannot configure.

#### Round 3: verify hop by hop with curl

A hypothesis needs an experiment. The method: **bypass the suspect layer and see whether the problem goes away**.

From inside the codespace, call nginx directly, with no port forwarder involved:

```bash
time curl -sS localhost:8080/api/query -H 'Content-Type: application/json' -d '{"question":"玩家受傷後的無敵時間在哪裡設定？"}'
```

Result: **success in 54.7 seconds**, with the full answer and citations.

[Screenshot: curl through nginx inside the codespace succeeding, time showing 54.7 s]

The same query from the browser through the forwarded URL: **504 after about 100 seconds**.

| Path | Result |
| --- | --- |
| `curl` inside the codespace → nginx → backend → Ollama | Success in 54.7 s |
| Browser → port forwarder → nginx → backend → Ollama | 504 after about 100 s |

The first path proves nginx, the backend and Ollama are fine. The only difference is the port forwarder, so the scope is down to a single layer.

(Why the browser request took longer than 54.7 seconds, long enough to hit 100: the model not being loaded yet, a different `top_k` (the `curl` query used 4; the browser request's value was not recorded), or queuing behind another request. Not confirmed yet: {待填}.)

[Screenshot: browser DevTools Network panel, /api/query returning 504 after about 100 s]

#### Fix: keep the connection from going idle by streaming the response

The original `/query` returns a single JSON only after the whole answer is generated, so during that minute of generation **not a single byte goes back to the browser**. If a proxy drops connections with no traffic, or only waits so long for the first byte, such a request gets cut no matter what the hops behind it are set to.

We cannot change the forwarder's limit, but we can change the shape of the request. I added `POST /query/stream`, which returns Server-Sent Events (ADR 0010):

| Event | When |
| --- | --- |
| `heartbeat` | Once immediately, then whenever nothing else has been sent for 10 seconds (`STREAM_HEARTBEAT_SECONDS`) |
| `sources` | As soon as retrieval finishes (within seconds), so the user sees the cited files first |
| `token` | Each time Ollama produces text |
| `done` | At the end, with `first_token_seconds`, `total_seconds` and other stats |
| `error` | For failures after the stream started (the HTTP status is already 200 and cannot change) |

nginx needs a separate location for the stream, with buffering off:

```nginx
location = /api/query/stream {
    proxy_pass http://backend:8000/query/stream;
    proxy_buffering off;
    proxy_cache off;
    gzip off;
    # ...
}
```

Another small trap here. I wrote a smoke test to confirm that it fails when a proxy buffers. With only `proxy_buffering on`, events still arrived one by one, so the test never failed. What actually held the stream back was **gzip**: with `gzip on` for `text/event-stream`, all 13 tokens of a 4-second answer arrived at the same instant at the end. The test's `curl` did not send `Accept-Encoding: gzip`, so nginx did not compress, and the problem stayed hidden. Browsers always send that header. The fix: `gzip off` in that location, plus `curl --compressed` in the smoke test, which now also checks that events arrive spread out over time.

The frontend uses `fetch` with a streaming reader and a small SSE parser (`EventSource` only supports `GET` without a body, and the question should not go in the URL). It shows the citations first, then the answer as it is generated, and finally the time to first token and the total time.

[Screenshot: the UI mid-stream, citations shown and the answer appearing token by token]

**Result**: in Codespaces, from the browser through the forwarded URL, I asked "Where is the invincibility time after the player gets hit configured?" (`qwen2.5-coder:3b`, `TOP_K=4`, first query after the model loaded). The stream completed: **time to first token 30.4 s, total 43.8 s, 129 tokens**, no 504.

| Run | Time to first token | Total | Notes |
| --- | --- | --- | --- |
| First (first query after model load) | 30.4 s | 43.8 s (129 tokens) | The 30.4 s before the first token is model load plus prompt processing |
| Same question again | 0.8 s | 14.3 s (134 tokens) | Ollama reused the cached prompt, so this is **not** normal latency; generation speed was about 10 tokens/s both times |

Read this result carefully. 43.8 seconds is **below** the roughly 100 seconds at which the non-streaming request was cut. It shows that a streamed query works through this forwarded URL; it does **not** show that the forwarder stopped limiting long queries. The 0.8 s on the second run comes from the cache and is not a latency figure either. A query longer than 100 seconds has not been tested, and it is still an open item in devlog 2026-11-02.

**Remaining risk**: if the forwarder limits the request's **total duration** rather than idle time, a long enough answer will still be cut. The next step then is an asynchronous query job plus polling, so every HTTP request stays short.

---

### Bonus: `git push` blocked by a Git LFS hook

This one has nothing to do with the services, but it is another environment difference that never shows up on a Mac, and it only surfaced after the dev container automation was in place.

**Symptom**: in the codespace, `git push` was refused before anything was sent, although the repository does not use Git LFS (no `.gitattributes`, no LFS files).

```text
This repository is configured for Git LFS but 'git-lfs' was not found on your path. If you no longer wish to use Git LFS, remove this hook by deleting the 'pre-push' file in the hooks directory (set by 'core.hookspath'; usually '.git/hooks').
```

**Hypothesis**: the message says the hook is there and the `git-lfs` binary is not. It does not say who installed the hook or why.

**Verification**: the clone had Git LFS hooks in `.git/hooks/` (`pre-push` and friends, which call `git lfs …`), but the dev container's base image (`mcr.microsoft.com/devcontainers/base:ubuntu-24.04`) does not include `git-lfs`, and `post-create.sh` did not install it. The hook exits with an error when `git-lfs` is missing, and a failing `pre-push` hook aborts the push.

**Fix**:
- `.devcontainer/post-create.sh` installs `git-lfs` together with `jq`, `zstd` and `iproute2`, then runs `git lfs install --skip-repo`. Plain `git lfs install` exits 2 when the hooks already exist (`Hook already exists: pre-push … run git lfs update --manual`), which would stop a `set -e` script and with it the whole `postCreateCommand`; `--skip-repo` only sets the global filter config.
- `scripts/doctor.sh` has a new check 12: it fails when LFS hooks exist but `git-lfs` does not, and prints the install command (and, since this repo has no LFS files, the alternative of deleting the hook). It does not depend on the services, so it runs last.
- For an existing codespace: `sudo apt-get update && sudo apt-get install -y git-lfs`, or rebuild the container.

The lesson matches the other pitfalls: an automated setup only contains what you have already tripped over (here, the list of `apt-get` packages), and each new kind of action (this time, push) can reveal a new gap.

---

## 4. Numbers

All numbers come from [`docs/metrics.md`](../../metrics.md) and the devlogs, with the environment noted. Codespaces and CI numbers are **CPU numbers and do not represent production performance on the Mac**.

### Codespaces (CPU, `qwen2.5-coder:3b`, `nomic-embed-text`)

| Metric | Value | Notes |
| --- | --- | --- |
| Machine type | 4 cores (devlog 2026-11-03) | `hostRequirements` in `devcontainer.json` asks for 4 cores / 16 GB; the actual machine type name: {待填} |
| Full index of the sample project | 20 files → 67 chunks, **41.9 s** (first full rebuild after an upgrade); 18.8–20.7 s (full rebuild after toggling `CHUNK_METADATA`) | Embeddings on CPU; the time of the very first index on 2026-11-01 was not recorded: {待填} |
| Prompt eval rate | **25.3 tokens/s** | `ollama run --verbose`, one run, Codespaces 4 cores (CPU), `qwen2.5-coder:3b`. Same run: generation (eval) 12.4 tokens/s, model load ≈ 3.5 s (metrics §3) |
| Generation (eval) rate | **About 10 tokens/s** | From two manual streaming queries (metrics §3), not a separate measurement |
| One query (non-streaming `/query`, `curl` through nginx) | **54.7 s** | One query, `top_k` 4 |
| Browser through the port forwarder (non-streaming) | 504 after about 100 s | |
| Streaming query (browser through the forwarded URL): time to first token / total | **30.4 s / 43.8 s** (129 tokens) | `TOP_K=4`, first query after model load; same question again: 0.8 s / 14.3 s, which is the prompt cache |
| `scripts/evaluate.py`, mean of 10 questions (`TOP_K=4`) | Time to first token 13.0 s, total 20.9 s (baseline group A) | 10 different questions after a warm-up, main set; see metrics §4a and article 6 |
| Codespace creation until the UI can answer | {待填} | First start |

How to read the prompt eval and eval rates: on CPU, one RAG query takes roughly

```text
total ≈ retrieval + prompt tokens ÷ prompt eval rate + answer tokens ÷ eval rate
```

A RAG prompt carries `TOP_K` code chunks and is usually much longer than the answer, so **time to first token is dominated by prompt eval**. That is why `TOP_K` went down from 8 to 4. The streamed query produced 129 tokens: at about 10 tokens/s that is roughly 13 s of generation, which matches the total of 43.8 s minus the first token at 30.4 s = 13.4 s (Ollama's own counter later gave 12.4 tokens/s for generation, so the real rate is a little higher). The other 30.4 s is model load plus prompt processing; the load took only about 3.5 s in the `ollama run --verbose` run, so most of it is prompt processing at 25.3 tokens/s. Prompt token count: {待填}.

### CI (GitHub Actions runner, CPU, first run, no caches)

| Job | Time |
| --- | --- |
| Backend unit tests | 40 s |
| Compose config check | 5 s |
| Image builds (backend / frontend) | 76 s / 45 s |
| End-to-end smoke test (including installing Ollama and pulling models) | 2 min 41 s |
| Full index during the smoke test (20 files / 67 chunks) | 21.54 s |
| One query during the smoke test (`qwen2.5-coder:0.5b`, `TOP_K=4`) | 8 s |

The smoke test deliberately uses the 0.5B model. It answers "does the pipeline run?", not "is the answer good?", and 0.5B is about 0.4 GB, quick to download and quick to run (ADR 0008). The embedding model stays the production `nomic-embed-text`, so the real vector size and prefixes are tested.

### Engineering quality

| Item | Value |
| --- | --- |
| Backend unit tests | 56 after the timeout work, 70 after streaming (about 2 s, no network); 170 on `main` at the time of writing (about 7 s, metrics §6) |
| Problems found in Codespaces that unit tests could not catch | The three pitfalls in this article plus the Git LFS bonus (full list from the test log: {待填}) |

### Mac M2 (not measured yet)

| Metric | Value |
| --- | --- |
| 14B generation rate (Metal) | {待填} tokens/s |
| 14B average query time | {待填} s |
| Same Mac, CPU in Docker vs. native Metal | {待填} |

---

## 5. Working with an AI coding agent

Most of the code in this project was written by Claude Code cloud sessions.

### What the cloud sessions did

- **Initial build**: backend, tree-sitter chunking, incremental indexing, the API, the React UI, Dockerfiles, compose, scripts, README and the sample project, plus unit tests with fakes. It also ran an end-to-end test in its sandbox with a real Qdrant and a fake Ollama server, which caught a bug the unit tests missed (the `text-dense` vector name; see devlog 2026-10-30).
- **Turning my test log into fixes**: I handed it my Codespaces test log, and it produced the configurable timeouts, the clear 504 messages, GitHub Actions CI (with a smoke test against a real Ollama), streaming responses, the dev container and `doctor.sh`, with an ADR for each decision.
- **Checking its own work**: for the streaming buffering issue, it first made the test fail on purpose with a broken nginx config, to prove the test could catch the problem, before handing over the fix.

### What I did

- **Set the architecture constraints**: Ollama stays out of Docker, code never leaves the machine, one compose file for every environment. These are requirements; the agent cannot decide them for me.
- **Ran it in real environments**: the cloud sandbox has no GPU, no real model, and is not Codespaces. I hit all three pitfalls myself in Codespaces, traced them myself with `curl` hop by hop, and wrote them up as a test log to hand back. **The agent fixes things fast, but it cannot see an environment it has never run in.**
- **Judged whether a hypothesis held up**: the observation that the 504 hit at 100 seconds, not 300, because the numbers did not match, was the turning point.
- **Reviewed every PR** and decided which numbers could go into the docs. Anything not measured stays `{待填}`.

### Cost

Claude Code cost: the first session, which built the initial version, was about **USD 7** (metrics §1); the session for PR #3 cost about **USD 10**, and all sessions together about **USD 100**, at which point the credit ran out (metrics §1; the split of the remaining USD 83 is not itemised). Codespaces core-hours: {待填}. GitHub Actions runs on GitHub-hosted runners for a public repo.

In one sentence: **an AI agent drives the cost of writing code way down, but the cost of verifying it in a real environment stays the same.** What actually saves time is writing verification results down concretely (symptom, command, error message, numbers) and handing that to the agent.

---

## 6. Wrap-up and next steps

Looking back, the three pitfalls have this in common:

1. **None was a logic bug.** The unit tests passed (70 at the time) and CI was green. The problems were network topology, process lifecycle and proxy timeouts.
2. **None happens on a Mac.** Docker Desktop handles `host.docker.internal` and loopback forwarding, the app starts Ollama for you, and there is no port forwarder locally. They only surfaced on Linux.
3. **All were solved the same way: test from where the caller sits, one layer at a time.** A `curlimages/curl` container to see the backend container's network; `ss` to check the process and its listen address; `curl` inside the codespace to bypass the forwarder. Each step ruled out one layer until a single suspect was left.

In the end, these steps became checks in `scripts/doctor.sh` and in CI, so next time the same problem shows up, nobody has to remember them.

Next steps:

- [ ] **Test on a real Mac M2**: measure 14B generation rate and query time on Metal, and compare CPU-in-Docker against native Metal on the same machine, to back ADR 0002 with numbers.
- [ ] **Compare with the 14B model**: using the 10 questions in `docs/evaluation/questions.md`, compare 3B and 14B on correctness, citation accuracy, and whether the trick question (online multiplayer sync, which the sample project does not have) leads to hallucination.
- [ ] Test a streaming query **longer than 100 seconds** from the browser in Codespaces and confirm the forwarder does not cut it (the 43.8-second run is not enough to show that).
- [ ] Stop and start the codespace, confirm Ollama and the stack come back by themselves (`./scripts/doctor.sh`), and record the time from creation until the UI can answer.

Source code, ADRs and devlogs are all in the repo: {待填: repo URL}

---

## Appendix A: title options

1. Deploying a local LLM: how I traced an unreachable Ollama and a 504 stuck at 100 seconds, one layer at a time
2. All unit tests passed, and it still broke three times in Codespaces: debugging an on-prem RAG deployment
3. It wasn't nginx: tracing a 504 timeout to the Codespaces port forwarder

## Appendix B: LinkedIn summary (about 150 words)

I built an on-prem RAG system for asking questions about a game front-end codebase: Ollama on the host, with Qdrant, FastAPI and a React UI in Docker. With no Mac available, I tested it first in GitHub Codespaces on CPU only. Every unit test passed, and it still broke three times. Containers could not reach Ollama, because Linux has no host.docker.internal and Ollama listens only on 127.0.0.1. After a restart, indexing failed because Ollama does not start again by itself. Queries returned 504 at about 100 seconds. Running curl inside the codespace succeeded in 54.7 seconds, which pointed to the Codespaces port forwarder, not nginx. Streaming the response got queries through. This post walks through each problem as symptom, hypothesis, verification and fix, with measured numbers, and what I still had to do myself when working with an AI coding agent.

## Publishing checklist

- [ ] Every path, symbol and screenshot comes from `examples/sample-game-frontend/` or this repo.
- [ ] Every number is checked against `docs/metrics.md`, a devlog or an evaluation report, with its environment stated.
- [ ] Add the cost of every Claude Code session and the total to `metrics.md` §1.
- [ ] Fill in every `[Screenshot: …]` and `{待填}`.
- [ ] Keep the Chinese version in sync with any change.
- [ ] After cross-posting, add the links back to `article-series.md`.
