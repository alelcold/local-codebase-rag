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
- `frontend/nginx.conf`: `proxy_pass http://backend:8000/` uses Compose service-name DNS.
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
- `frontend/nginx.conf`：`proxy_pass http://backend:8000/` 使用 Compose 的服務名稱 DNS。
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
