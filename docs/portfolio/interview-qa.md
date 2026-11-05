# 面試準備：地端 Codebase RAG

> **語言**：繁體中文為主，英文版附在下方（[跳到英文版](#english-version)）。這和 `CLAUDE.md`「先英文、再中文」的規則相反，與 `article-series.md` 的中英文分檔一樣，是為了方便複習與面試時使用而做的例外。
> **數字規則**：所有數字只來自 repo 的 `docs/metrics.md`、`docs/decisions/`、`docs/devlog/`、`docs/evaluation/results/`；沒量過的保留 `{待填}`。每題最後的「出處」是複習時查證用的。
> **三個要先講清楚的前提**（面試時被追問，先自己講比被抓到好）：
> 1. 所有實驗在 **Codespaces、4 核心 CPU、`qwen2.5-coder:3b`、`TOP_K=4`**、20 個檔案的範例專案上做，**每組只跑一次**。Mac M2 + 14B 的數字目前全是 `{待填}`。
> 2. 「人工判定正確性」是 **AI（Claude）評分**，只有 5 個最不確定的分數由人複查（結論沒變），其餘未經人確認（[ADR 0018]、[devlog 2026-11-05]）。
> 3. 程式碼大部分由 Claude Code 雲端工作階段寫成：第一版約 7 美元，到目前所有工作階段約 100 美元（[metrics §1]）。
> **隱私**：所有檔名與符號都來自 `examples/sample-game-frontend/` 或本 repo。

---

## 1. 專案介紹稿

### 30 秒版

我做了一套**地端的程式碼問答系統**：團隊可以用中文問遊戲前端專案「無敵時間在哪裡設定」這類問題，系統會取回相關程式碼，回答並附上 `檔案:行號` 引用。LLM（Ollama 的 `qwen2.5-coder`）、向量資料庫（Qdrant）都跑在自己的機器上，**程式碼和問題都不離開本機**。我另外建了自動化評估，用 8 組對照實驗決定哪些檢索技巧值得開，結果只有「分類取回」值得預設開啟，其他常見技巧（混合檢索、rerank、相似度門檻等）都用數據淘汰。

### 2 分鐘版

**問題**：遊戲前端專案大約 50～300 個檔案，新人最常問「X 在哪裡設定？」，grep 找得到字串，但回答不了「怎麼串起來」。雲端 AI 助手可以，但程式碼不能離開公司的機器，而且團隊需要的是共用工具（[ADR 0001]）。

**架構**：Ollama 直接跑在主機上（Mac 要用 Metal GPU，Docker 用不到，[ADR 0002]），Qdrant、FastAPI + LlamaIndex 後端、React 前端跑在 Docker 裡。索引時用 tree-sitter 依函式與 class 切塊、Markdown 依標題切塊，每個引用都對應精確行號（[ADR 0004]），並依內容雜湊做增量索引。回答用 Server-Sent Events 串流，避免代理在長時間沒有資料時切斷連線（[ADR 0010]）。

**我學到最多的兩件事**：
- **除錯**：在 Codespaces 上，單元測試全過，部署卻壞了好幾次。最典型的是查詢在約 100 秒回 504：我們自己的逾時是 300 秒，用 `curl` 繞過轉發，同一題 54.7 秒成功，才定位到是 Codespaces 的連接埠轉發（[ADR 0009]、[ADR 0010]）。
- **實驗**：第一個問題是「無敵時間在哪裡設定」取回的 4 個片段全是 Markdown。我先做評估工具，再固定條件、一次只改一個開關，試了混合檢索、分類取回、metadata、rerank、相似度門檻、防幻覺 prompt。結果分類取回讓取回內容中的文件比例從 95% 降到 25%、程式碼檔命中 1/9 → 6/9，AI 評分的正確性 11 → 17（滿分 30）；常見的 0.70 門檻會丟掉 93% 的正確片段；防幻覺 prompt 拒答了 9 題可回答題中的 8 題。

**限制**：只有 20 個檔案的範例專案、每組跑一次、3B 的 CPU 模型，Mac 14B 還沒實測；正確性是 AI 評分。第一版用 Claude Code 一個工作階段約 7 美元完成，我負責架構限制、在真實環境驗證、判斷假設對不對。

---

## 2. 20 題面試問答

> 每題格式：**問題** → **參考回答**（口語、可直接講）→ **可能的追問**（若有）→ **出處**（複習時查證）。

### A. 架構選擇

#### Q1. 為什麼要做地端，而不是直接用雲端 LLM API？

**參考回答**：三個原因。第一是隱私：原始碼是最敏感的資產，程式碼與問題不能離開公司機器，也不想去審查第三方的資料保留政策。第二是成本：使用量沒有上限（很多人、很多問題），按 token 計費很難預測，地端的邊際成本幾乎只有電費。第三是它要是團隊共用工具，不是每個人各付費各設定。

我也很清楚代價：14B 本機模型在多步推理上不如頂尖雲端模型，所以回答品質更依賴檢索品質，這也是我花那麼多力氣在切塊和評估的原因；吞吐量受限於一台機器，同時使用的人要排隊；維運（模型更新、Ollama 程序、磁碟）由團隊自己負責。

**可能的追問**：品質差距有多大？→ 還沒量到。14B 在 Mac 上的評估分數是 `{待填}`；目前只有 3B 在 Codespaces 的數字。如果品質不夠，ADR 的後續計畫是先在 GPU 機器上測更大的模型，再考慮雲端 API。

**出處**：[ADR 0001]（替代方案表：雲端 API、雲端 LLM + 本地向量庫、IDE 助手、grep）、[metrics §5]（Mac 與 14B 的欄位為 `{待填}`）。

#### Q2. 為什麼 Ollama 不放進 Docker？

**參考回答**：因為 Mac 上的 Docker Desktop 是在 Linux 虛擬機裡跑容器，Apple 的 Metal GPU 不會傳進虛擬機，所以放進 compose 的 Ollama 在 Mac 上只能用 CPU，14B 模型會慢到不能用。另外 Apple Silicon 是統一記憶體，給 Docker VM 的記憶體會被保留，原生程序則可以彈性使用。

所以決定是：Ollama 一律在主機上原生執行，容器用 `host.docker.internal:11434` 呼叫。代價是安裝分兩段（主機裝 Ollama + compose），而且各平台行為不同，Linux 上要多做兩件事（`host-gateway` 與 `OLLAMA_HOST=0.0.0.0`，見 Q15）。

**可能的追問**：你有量過 CPU 和 Metal 差多少嗎？→ 還沒有。ADR 的後續待辦就是補這個數字，目前 Mac 的數字都是 `{待填}`，我不會編造。

**出處**：[ADR 0002]（替代方案：容器版 Ollama、GPU passthrough、llama.cpp、LM Studio/MLX）、[ADR 0006]、[article 3]、[metrics §3]（Mac 欄位 `{待填}`）。

#### Q3. 為什麼選 Qdrant，不是 Chroma、pgvector 或 FAISS？

**參考回答**：規模很小（最多幾千個向量），所以效能不是決定因素，運維簡單和功能才是。我需要的是：相似度搜尋要回傳 metadata（給引用用）、**依檔案刪除所有片段**、**列出已索引檔案與其雜湊**（給增量索引用），而且要能在 Docker 裡持久化、單元測試不用起伺服器。Qdrant 的 payload filter 讓「依檔案刪除」很直接，記憶體模式讓單元測試很快，還有內建的網頁 dashboard 可以 debug。

Chroma 比較簡單但過濾與維運功能較少；pgvector 要多一個 Postgres 和 schema；FAISS 沒有 metadata 與過濾；Milvus 對幾千個向量太重。

**可能的追問**：有踩過坑嗎？→ 有。LlamaIndex 的 `QdrantVectorStore` 只在建構時檢查 collection 的向量佈局。API 程序在索引存在之前就建好 store，後來 CLI 索引器（另一個程序）建了 collection，API 就一直查詢不存在的向量名稱 `text-dense`，每個 `/query` 回 502。單元測試每次只用一個 store 實例，所以沒抓到；端到端測試才抓到。

**出處**：[ADR 0003]、[devlog 2026-10-30]（Problem 1，含完整錯誤訊息）。

#### Q4. 為什麼用 SSE 串流，而不是 WebSocket、EventSource 或輪詢？

**參考回答**：起因是 Codespaces 的 504。原本的 `/query` 要等整個回答生成完才回一個 JSON，生成的那一分鐘裡連一個 byte 都不會送回瀏覽器，代理只要會切斷沒有流量的連線，就會被切，無論後面怎麼設逾時。所以我改變請求的形狀：新增 `POST /query/stream`，先馬上送一個 heartbeat，之後每 10 秒沒有輸出就再送，接著送引用（`sources`）、逐 token 送 `token`、最後送含耗時統計的 `done`。

不選 WebSocket：流量是一個請求對一個串流，雙向沒有價值，還要每個代理都設 Upgrade，更難用 `curl` 測。不選 `EventSource`：它只支援不帶 body 的 GET，問題會進網址與 access log，而且自動重連會重跑整個生成。輪詢（非同步工作）是最徹底的做法，每個 HTTP 請求都很短，但要新增狀態與儲存，我把它留作後備方案。

**可能的追問**：串流真的解決了嗎？→ 部分。在 Codespaces 從瀏覽器經轉發網址完成了一次串流查詢（首字延遲 30.4 秒、總耗時 43.8 秒、129 個 token），沒有 504。但 43.8 秒低於非串流版被切斷的約 100 秒，所以它證明「串流走得通」，**不**證明轉發不再限制長查詢；超過 100 秒的查詢還沒測。

**出處**：[ADR 0010]（含替代方案表）、[ADR 0009]、[devlog 2026-11-02]（Problem 1、2）、[metrics §3]。

### B. RAG 原理

#### Q5. 說明 embedding 與向量檢索怎麼運作，你的設定有什麼細節？

**參考回答**：索引時，每個片段送進 embedding 模型（`nomic-embed-text`，約 0.3 GB）轉成向量存進 Qdrant；查詢時，把問題轉成向量，找 cosine 最相近的片段，取前 `TOP_K` 個放進提示詞給 LLM。

細節有三個。第一，`nomic-embed-text` 需要前綴：文件用 `search_document: `，問題用 `search_query: `。我踩過一個靜默的 bug：Compose 把沒設定的變數當成空字串傳進去，pydantic 把 `""` 當成「明確不要前綴」，不會報錯，只會讓檢索品質變差；修法是把空字串視為「自動」，並加測試。第二，送給 embedding 的文字有檔案路徑與符號名稱的標頭，但儲存的是原始程式碼，所以引用顯示的是原始行。第三，collection 依 embedding 模型命名，換模型是安全的。

我也知道一個弱點：中文問題對上英文為主的 embedding 模型，檢索可能比英文問題差，這是在 ADR 0005 就標註的風險，也是本專案文件（中文）永遠贏過程式碼（英文）的原因（見 Q13）。

**出處**：[ADR 0005]（embedding 選擇與風險）、[ADR 0004]、[devlog 2026-10-30]（Problem 2）。

#### Q6. 你的 chunking 策略是什麼？為什麼不用固定大小切塊？

**參考回答**：依檔案類型切。TypeScript/JavaScript 用 **tree-sitter** 解析，每個頂層函式、class、interface、type、enum 或 React 元件各成一塊，JSDoc 跟著宣告走；import 與其他頂層敘述合成 `module` 塊；過大的 class 依 method 再切；仍然太大就用行視窗加 3 行重疊。Markdown 依標題切（忽略 code fence 裡的 `#`），每塊記錄標題路徑，例如「玩法規則 > 計分」。上限 `CHUNK_MAX_CHARS` 預設 3000。

為什麼不用固定大小：它會把函式切一半、一個 chunk 混兩個不相干的函式，也沒有符號名稱，而我需要**精確行號**做引用（`src/entities/Player.ts:16-113`），測試會檢查行號與原始碼一致。範例專案 20 個檔案切成 67 個片段。

代價：依賴 tree-sitter 套件版本要釘住；小 helper 變成很小的塊，會用掉更多 `TOP_K` 名額；跨很多檔案的問題（例如「列出所有元件」）仍然不適合 chunk 層級的 RAG。

**可能的追問**：改了切塊設定會怎樣？→ `file_hash` 包含 chunker 版本與 `CHUNK_MAX_CHARS`，所以會自動重新切塊；`index_config`（含 embedding 設定）改變時會自動全量重建索引。

**出處**：[ADR 0004]、[ADR 0013]（settings fingerprint）、[metrics §2]（20 檔／67 片段）。

#### Q7. 什麼是混合檢索與 RRF？你實作了什麼？

**參考回答**：向量檢索擅長語意，但對精確識別字弱：問題裡的 `INVINCIBLE_MS` 在 embedding 空間只是眾多 token 之一。混合檢索是同時跑多個檢索器，再合併排名。我做了三個通道：向量、BM25 關鍵字、以及「識別字定義比對」（問題中看起來像程式碼的詞，大小寫敏感地比對各片段**宣告**的名稱）。

合併用 **RRF（Reciprocal Rank Fusion）**：`score = Σ 1/(k + rank)`，`k=60`。它只看排名，不需要把 cosine 和 BM25 分數正規化到同一個尺度；被多個檢索器同時找到的片段會被拉高。

一個我自己踩到的坑：BM25 一開始對中文用字元 bigram，結果中文文件的每個 bigram 都只比對得到文件，蓋過唯一的精確識別字，關鍵字通道反而在放大文件擠掉程式碼的問題。修正是 BM25 只索引 ASCII 單字、識別字與數字，中文語意交給向量通道。代價是：不含識別字的中文問題，BM25 無從比對。

**出處**：[ADR 0013]（RRF、tokenizer、替代方案）、[devlog 2026-11-02]（Problem 5、6）、[article 6]。

#### Q8. Rerank 是什麼？為什麼你沒有預設開啟？

**參考回答**：Rerank 用 cross-encoder 把（問題, 片段）一起輸入模型打分，比 embedding 的 cosine 更準，通常放在檢索之後，對前 N 個候選重新排序。我實作成選用：取回 10 個候選、重排後留 `RERANK_TOP_N`，用 `BAAI/bge-reranker-base`（278M；`v2-m3` 更強，但 10 組要 11.97 秒，base 只要 3.73 秒）。

實驗結果：**單獨開沒用**（主題庫定義檔 0/3），因為它只能重排向量取回的 10 個候選，而這 10 個幾乎全是 Markdown；而且通用 reranker 偏愛文件，Markdown 得分 0.8～0.99，程式碼大多低於 0.1。搭配混合檢索加分類取回（I 組）時，主題庫定義檔 0/3 → 3/3，檢索最好。

但沒有預設開：每次查詢多 4.8 秒 rerank、首字延遲相對 D 組多約 10 秒（17.2 → 26.8 秒）、映像檔從 616 MB 變 2.14 GB，被推上來的程式碼 rerank 分數只有 0.0027 之類，排序脆弱。最關鍵的是 AI 評分的正確性 I 和 C 同樣是 17/30，檢索變好但答案沒有更好。

**出處**：[ADR 0015]、[ADR 0018]、[metrics §4a]、[metrics §4b]、[metrics §6]（映像檔大小）。

#### Q9. 為什麼相似度門檻（score threshold）沒有採用？

**參考回答**：客服型 RAG 常見的做法是設 0.70，低於就不呼叫 LLM、直接回「找不到」。我沒有憑感覺選，而是寫了 `calibrate_threshold.py`，從實驗報告收集所有取回片段的 cosine，分成「預期檔案的片段」與「其他片段」。結果兩者幾乎重疊：預期片段中位數 **0.616**（n=27），其他片段 **0.604**（n=63）。0.70 會丟掉 27 個正確片段中的 25 個（**93%**），讓 15 題中的 10 題失去所有預期片段；唯一能拒答陷阱題的 0.60，已經讓 6 題真實問題失去所有正確片段；≤ 0.45 安全，但什麼都擋不到。腳本的結論是「不建議任何數值」，所以這組實驗根本沒跑。

通用建議沒錯，但前提（分數能分辨相關性）在「中文問題 + 英文程式碼」的 codebase 不成立。要拒答不存在的功能，需要別的訊號。另外門檻值跟 embedding 模型綁定，換模型就要重新校準。

**出處**：[ADR 0014]、[calibration]、[devlog 2026-11-03]（Threshold calibration 一節）、[article 6]（4.4）。

### C. 實驗方法

#### Q10. 你怎麼設計實驗？為什麼對照組與「一次只改一個開關」很重要？

**參考回答**：先做評估工具再改東西。固定條件（Codespaces、4 核心 CPU、3B、`TOP_K=4`、暖機一題）、每個技巧都是預設關閉的 `.env` 開關、每組只改一個、跑完用 `/health` 確認開關與預期一致。用兩個題庫：10 題主題庫（用團隊平常的問法，大多沒有識別字）和 5 題識別字題庫（問題寫出識別字），因為我預期關鍵字類技巧只在後者有用。

對照組的價值有個具體例子：只看 A、B，我會宣布混合檢索有效（識別字題定義檔 33% → 100%）。補了 C（只有分類取回）才知道 C 單獨就 3/3；補了 D（混合 + 分類）才知道混合檢索在主題庫還擠掉了第 8 題（D 0/3 vs C 1/3）。同樣地，在 D 出現之前，我把 I 的功勞算給混合檢索，D 修正成 rerank。**每個「有效」都要問：把它拿掉，哪個開關其實已經做到了？**

另一個陷阱是延遲：B 組的首字延遲看起來快一倍（6.7 vs 13.0 秒），其實是 Ollama 重用了快取的提示詞；檢索時間每組都只有 0.07～0.21 秒。

**出處**：[experiment plan]（固定條件、決策規則）、[ADR 0012]、[devlog 2026-11-03]（Problem 1、Group D 一節）、[metrics §4a]、[article 6]。

#### Q11. 解釋拒答率與誤拒率，為什麼要一起看？

**參考回答**：拒答率是陷阱題（專案沒有的功能）被回答「找不到」而且沒有編造程式碼的比例；誤拒率是**可回答**的題目被回答「找不到」的比例。只看前者會被騙：prompt v3 加了一條明確規則「沒有片段直接提到就只回固定句」，範圍外陷阱題拒答率 **5/5**，第 10 題也拒答了；但同一張表的另一欄，主題庫 9 題可回答題誤拒 **8/9**、識別字題庫 2/5、對照題（專案有但容易被誤認為沒有的功能）3/3。23 個回答中有 19 個一字不差是固定句，連預期檔案已經全部取回的題目也被拒答。

決策規則是在實驗前就寫好的：誤拒率必須在每個題庫維持 0，因為錯誤的「找不到」會把真實存在的程式碼藏起來，一次誤拒比少拒答一題陷阱題更糟。所以 v3 不採用。我的假設（未驗證）是「沒有片段『直接』提到」是個判斷，3B 模型做不穩；v3 在 14B 上還沒試過。

**出處**：[ADR 0016]、[metrics §4c]、[devlog 2026-11-03]（Group J 一節）。

#### Q12. 你的評估指標有什麼限制？

**參考回答**：我把限制直接寫在 ADR 0012 的決策裡：
- **關鍵字命中不等於答對。** Codespaces 上那個錯誤回答同時含有 `INVINCIBLE_MS` 和 1500，卻說定義在 `docs/gameplay.md`。
- **檔案命中量的是取回了什麼，不是模型用了什麼。** 在 C 和 D 裡，第 7、9 題雖然取回了預期的程式碼檔，3B 模型還是從錯的檔案作答。
- **預期清單是我自己列的**，另一個片段也可能答得出來。
- **拒答偵測是字串比對**，而且真的出過洞：關鍵字只列了繁體的「無法」，範圍外第 22 題的簡體拒答「我无法提供…」被算成沒拒答；而第 23、25 題是編造的回答卻通過了檢查。修正在 ADR 0019：繁簡對照清單加上「檔案或符號在專案裡不存在」的檢查，並用 `--rescore` 重新計分舊報告，不重跑模型。這個檢查仍然是字面的，抓不到用真實名稱編造的行為（59 個 0 分的回答中只標出 29 個）。
- **正確性是 AI 評分**，不是人；只有 5 個最不確定的分數由人複查。
- 10 題是很小的樣本，一次只跑一遍，差一題是雜訊。

所以我在文章與履歷都明講「僅自動指標」或「AI 評分」，不把關鍵字命中率叫正確率。

**出處**：[ADR 0012]（Limitations）、[ADR 0019]、[ADR 0018]（Limits of the evidence）、[devlog 2026-11-05]。

#### Q13. 所以最後的結論是什麼？證據有多強？

**參考回答**：只有**分類取回**（`SPLIT_RETRIEVAL=true`、`DOC_TOP_K=1`）預設開啟，而且只套用在 Codespaces 的 `.env.codespaces`（ADR 0018），Mac 的 `.env.example` 沒改，等 Mac 實測。證據（主題庫，Codespaces 3B）：取回內容中文件比例 95% → 25%、程式碼檔命中 1/9 → 6/9、識別字題定義檔 1/3 → 3/3，檢索時間仍是 0.07～0.21 秒；AI 評分的正確性（兩個題庫共 30 分）從 11 提高到 17；重點在文件的第 2、3、6 題沒有退步（0/2/2 → 0/2/2）。

它為什麼有效：文件跟中文問題用同一種語言，在 embedding 空間永遠贏過英文程式碼；與其讓程式碼更像，不如保證程式碼有座位。

證據強度我會誠實說：效果大（split 對 baseline、v3 墊底）超出單次執行的雜訊，但 B、C、D、F、I 之間 16～17 分的差距不算數；每組跑一次、3B 會每次寫出不同的答案。另外第 2 題（連擊倍率）在 8 組全是 0，是任何開關都補不了的檢索缺口。

**出處**：[ADR 0018]、[metrics §4a]、[article 6]（4.2、4.7）。

### D. 除錯故事

#### Q14. 講一次你一層層排查的經驗：504 逾時。

**參考回答**（現象 → 假設 → 驗證 → 結論）：

- **現象**：Codespaces 上從瀏覽器問問題，等一陣子顯示 504。
- **假設 1**：我們自己的逾時太短。**驗證**：列出每一段實際設定——nginx 寫死 900 秒、LLM 逾時 600 秒、embedding 呼叫**完全沒有逾時**。504 在約 1.5～2 分鐘就出現，這兩段都不可能是放棄的那個，假設被推翻。我仍把全部逾時改成 `.env` 可設定、預設 300 秒，並讓逾時回傳說明階段與變數名稱的 504。
- **轉折**：修完仍然在**約 100 秒**被切，跟 300、600、900 都對不上，代表放棄的是另一段連線。
- **假設 2**：nginx 前面的 Codespaces 連接埠轉發。**驗證**：繞過它——在 codespace 裡直接 `curl` nginx，同一題 **54.7 秒成功**；從瀏覽器經轉發網址則約 100 秒後 504。nginx、後端、Ollama 已被第一條路徑證明沒問題，範圍縮到一層。
- **結論與修正**：轉發的上限我們改不了，但可以改請求形狀——改成 SSE 串流（Q4）。

兩個小插曲：`curl -s` 把錯誤訊息一起藏起來，之後一律用 `-sS`；我寫的串流測試本來永遠不會失敗，因為真正卡住串流的是 gzip 而不是 `proxy_buffering`，測試用的 `curl` 沒送 `Accept-Encoding: gzip` 所以問題被藏起來了，後來改成 `curl --compressed` 並檢查事件是否分散在不同時間到達，也用故意弄壞的設定確認測試真的會失敗。

**出處**：[ADR 0009]（修改前設定表）、[ADR 0010]、[devlog 2026-11-01 Codespaces]（Problem 3、5）、[devlog 2026-11-02]（Problem 1、2）、[article 3]。

#### Q15. `host.docker.internal` 在 Linux 上為什麼不通？怎麼查的？

**參考回答**：現象是 `/health` 回報連不到 Ollama，但在 codespace 終端機裡 `curl localhost:11434` 是通的。關鍵觀念：「我這裡連得到」和「容器連得到」是兩件事——容器裡的 `localhost` 是容器自己，連主機走的是 Docker bridge 的 gateway。所以有兩個嫌疑：名稱解析和監聽位址。

驗證要**從呼叫端的位置測**：開一個用完即丟的容器，`docker run --rm --add-host=host.docker.internal:host-gateway curlimages/curl -sS http://host.docker.internal:11434/api/version`，它看到的網路和後端容器一樣。再用 `ss -ltnp | grep 11434` 看 Ollama 聽在哪：預設 `127.0.0.1`，bridge 進來的連線會被拒絕。

兩個原因都修：compose 加 `extra_hosts: host.docker.internal:host-gateway`（Docker Desktop 上無害，Linux 上必要），並以 `OLLAMA_HOST=0.0.0.0` 啟動 Ollama。Mac 不會遇到，因為 Docker Desktop 自動解析並轉到主機 loopback。

資安提醒：`0.0.0.0` 讓 11434 在所有網卡上開放，而 Ollama 沒有驗證；所以 `devcontainer.json` 把 11434 與 6333 設為 `ignore`（永遠不轉發），EC2 用 security group 擋。

**出處**：[devlog 2026-11-01]（Problem 1）、[devlog 2026-11-01 Codespaces]（Problem 3、4）、[ADR 0006]、[ADR 0011]、[article 3]。

#### Q16. Git LFS 的問題是什麼？

**參考回答**：在 codespace 裡 `git push` 還沒送出任何東西就被拒絕，但這個 repo 根本沒用 Git LFS（沒有 `.gitattributes`、沒有 LFS 檔案）。錯誤訊息是 `This repository is configured for Git LFS but 'git-lfs' was not found on your path…`。

原因：clone 裡的 `.git/hooks/` 有 Git LFS 的 hook（`pre-push` 等，會呼叫 `git lfs …`），但 dev container 的基底映像（`mcr.microsoft.com/devcontainers/base:ubuntu-24.04`）沒有 `git-lfs` 執行檔，`post-create.sh` 也沒裝。hook 缺少 `git-lfs` 時以錯誤結束，`pre-push` 失敗就中止 push。

修正：`post-create.sh` 把 `git-lfs` 跟 `jq`、`zstd`、`iproute2` 一起裝，再跑 `git lfs install --skip-repo`——不加 `--skip-repo` 時，hook 已存在會以 2 結束（`Hook already exists: pre-push … run git lfs update --manual`），在 `set -e` 的腳本會讓整個 `postCreateCommand` 中斷。`doctor.sh` 新增第 12 項檢查，缺 `git-lfs` 時印出安裝指令（也列出刪除 hook 的替代做法）。

教訓：自動化環境的清單只包含你踩過的坑，每換一種動作（這次是 push）就可能冒出新的缺口。

**出處**：[devlog 2026-11-03]（Problem 3）、[ADR 0011]、[article 3]（番外）。

### E. 用 AI coding agent 開發

#### Q17. 你負責什麼、AI 負責什麼？

**參考回答**：AI（Claude Code 雲端工作階段）做了初版建置：後端、tree-sitter 切塊、增量索引、API、React 介面、Dockerfile、compose、腳本、README、範例專案與單元測試，約 7 美元、一個工作階段。後續它也把我的測試紀錄變成修正：可設定的逾時、CI、串流、dev container、`doctor.sh`、評估腳本與實驗報告，每個決策都寫成 ADR。

我負責的是 AI 沒辦法替我決定、或看不到的部分：
- **架構限制**：Ollama 不放 Docker、程式碼不離開本機、一個 compose 檔跑所有環境，這些是需求。
- **在真實環境上跑**：雲端 sandbox 沒有 GPU、沒有真實模型、也不是 Codespaces。三個坑都是我在 Codespaces 親手撞到、用 `curl` 一層層查，再寫成測試紀錄交回去的。AI 修得很快，但它看不到它沒跑過的環境。
- **判斷推測對不對**：504 斷在 100 秒而不是 300 秒，這個「數字對不上」的觀察是轉折點。
- **審查每個 PR，並決定哪些數字可以寫進文件**，沒量過的一律 `{待填}`。

誠實補充：後期的「人工判定正確性」是 AI 評分，不是我，這是目前最弱的環節。成本方面，第一版約 7 美元，到目前所有工作階段約 100 美元（額度用完）。

**出處**：[article 3]（第 5 節）、[ADR 0001]（註記）、[metrics §1]、[ADR 0018]。

#### Q18. 你怎麼驗證 AI 的產出？

**參考回答**：分四層，每層回答一個問題，由便宜到貴（ADR 0007）：單元測試用假物件驗邏輯（現在 183 個，約 7 秒、不需網路）；compose 與映像檔檢查；端到端冒煙測試（CI 上裝真的 Ollama、用 0.5B 模型，驗證流程而不是品質）；最後是在目標環境手動跑。品質只在目標模型與硬體上判斷，不用 0.5B 或 3B 當作品質結論。

具體例子：
- AI 自己在 sandbox 用真實 Qdrant 加假的 Ollama server 跑端到端，抓到單元測試漏掉的 `text-dense` 向量名稱 bug（跨程序狀態，記憶體假物件看不到）。
- 串流緩衝問題：先用有問題的 nginx 設定讓測試失敗，確認測試真的抓得到，才交出修正（`✗ All events arrived within 0.00s although the backend streamed for 4.321s.`）。
- 實驗本身：讓評估腳本跑出數字、對照組校正結論、把限制寫進 ADR；腳本的洞（簡體拒答、編造的回答）也是讀回答才發現的，再補測試與 `--rescore`。

我的原則：把驗證結果寫成具體紀錄（現象、指令、錯誤訊息、數字）再交給 agent，並且每個數字都標環境與來源。

**出處**：[ADR 0007]、[ADR 0008]、[devlog 2026-10-30]（Problem 1）、[devlog 2026-11-02]（Problem 2）、[ADR 0019]、[metrics §6]。

### F. 重來與限制

#### Q19. 如果重來，你會怎麼做不同？

**參考回答**：
1. **更早在真實目標環境驗證。** 三個部署坑都是單元測試與 CI 抓不到的環境問題；我會更早在 Linux 預演環境與 Mac 上各跑一次完整流程，而不是等到最後。Mac 的所有數字現在都是 `{待填}`，這是最大的缺口。
2. **實驗一開始就做重複執行與隨機化順序。** 現在每組只跑一次，提示詞快取又會干擾延遲，B 組「快一倍」就是例子；我會交錯順序跑兩次，估計雜訊。
3. **人工評分一開始就排進流程**，並且由人做。現在正確性是 AI 評分，結論的最後一哩要靠這個確認。
4. **成本與數據當天記錄。** 現在 Claude Code 的費用只有第一版約 7 美元與 PR #3 約 10 美元是分開記的，其餘合計約 100 美元沒有逐項記錄。
5. **小流程防呆**：兩份 ADR 同時被編成 0016（各自取了當時的「下一個號碼」），後來要改名；我會加一個檢查編號是否重複的測試。

**出處**：[metrics §1]、[metrics §2]、[metrics §3]、[devlog 2026-11-05]（Problem 1）、[ADR 0018]（Follow-ups）。

#### Q20. 目前的限制是什麼？下一步呢？

**參考回答**：
- **規模**：範例專案只有 20 個檔案、67 個片段（其中 3 個是 Markdown）；真實專案是 50～300 個檔案，候選池、BM25 行為、cosine 分布都可能不同，「文件上限 1」在大專案可能要重新看。
- **實驗**：每組一次，Codespaces、4 核心 CPU、3B、`TOP_K=4`、中文問題；結論不能自動搬到 Mac、14B 或 `TOP_K=8`。
- **正確性**：AI 評分，5 個最不確定的分數由人複查，其餘未經人確認。
- **檢索缺口**：第 2 題（連擊倍率）在 8 組全是 0，因為中文問題沒有識別字，沒有任何開關能取回 `ScoreSystem.ts`。
- **評估**：編造偵測是字面的，抓不到用真實名稱編造的行為。
- **產品面**：單機吞吐量；簡體字漂移（3B 模型壓不住，v2 prompt 後仍有 2 個）。

下一步（都在 ADR 與 devlog 的待辦裡）：在 Mac 上跑 `./scripts/benchmark-mac.sh` 並另外決定 Mac 預設（ADR 0017、0018）；測「分類取回 + rerank、不含混合檢索」；中文 → 識別字對照表給關鍵字通道；重跑各組以估計雜訊；由人確認剩餘的評分；超過 100 秒的串流查詢與 codespace 停止再啟動的實測。

**出處**：[ADR 0018]（Consequences、Follow-ups）、[devlog 2026-11-05]（Next）、[ADR 0019]、[article 6]（第 7、8 節）、[metrics §3]。

---

## 3. 一頁式專案摘要（STAR）

> 可直接放進作品集網站。數字都來自 repo，環境是 Codespaces、4 核心 CPU、`qwen2.5-coder:3b`、`TOP_K=4`、20 個檔案的範例專案、每組實驗一次；人工判定正確性為 AI 評分。

### 地端 Codebase RAG 問答系統

`Python` `FastAPI` `LlamaIndex` `Qdrant` `Ollama` `React` `Docker` `GitHub Actions` ｜ [GitHub](https://github.com/alelcold/local-codebase-rag)

**Situation（情境）**
遊戲前端團隊的專案大約 50～300 個檔案，新人最常問「X 在哪裡設定？」。grep 找得到字串，但回答不了「怎麼串起來」；雲端 AI 助手可以回答，但原始碼不能離開公司的機器，而且團隊需要共用的工具。

**Task（任務）**
在一台機器上建置完整的 RAG 流程：用自然語言（中文）提問，回答附 `檔案:行號` 引用，程式碼與問題都不離開本機。並且用數據、而不是直覺，決定哪些檢索技巧值得開啟。

**Action（行動）**
- **系統**：Ollama 原生執行在主機（為了 Mac 的 Metal GPU）；Qdrant、FastAPI + LlamaIndex、React 在 Docker。用 tree-sitter 依函式／class 切塊、Markdown 依標題切塊，依內容雜湊增量索引。回答以 SSE 串流，繞過 Codespaces 連接埠轉發在約 100 秒切斷連線的 504。
- **維運**：同一份 compose 支援 Mac、Codespaces、Linux GPU 機器；dev container 在每次啟動時自動準備 Ollama、模型、服務與索引；12 步驟的 `doctor.sh` 為每項失敗印出修正指令；GitHub Actions CI 含端到端冒煙測試。
- **實驗**：先建自動化評估（`evaluate.py`；10＋5＋8 題），固定條件、一次只改一個開關，跑 8 組對照實驗與 1 次門檻校準，並用對照組修正自己的結論（混合檢索的增益其實分類取回就做到了）。
- **AI 協作**：用 Claude Code 雲端工作階段在約 7 美元內完成第一版；我負責架構限制、在真實環境驗證與判斷假設，並把驗證結果寫成具體紀錄再交回去。

**Result（結果）**
- **分類取回**：取回內容中的文件比例 95% → 25%、程式碼檔命中 1/9 → 6/9、識別字題定義檔命中 1/3 → 3/3，檢索時間仍是 0.07～0.21 秒；AI 評分的正確性 11 → 17（滿分 30）。已套用到 Codespaces 預設設定（ADR 0018）。
- **被數據淘汰的 6 種做法**：混合檢索（分類取回之上沒有額外效果）、chunk metadata 與 prompt v2（沒有改善）、相似度門檻（0.70 會丟掉 93% 的正確片段）、rerank（+4.8 秒、約 +10 秒首字延遲、映像檔 616 MB → 2.14 GB，正確性與分類取回同為 17/30）、拒答 prompt v3（9 題可回答題誤拒 8 題）。
- **工程**：串流查詢在轉發網址上完成（首字延遲 30.4 秒、總耗時 43.8 秒）；183 個單元測試約 7 秒、不需網路；第一版以約 7 美元的 AI 工作階段完成。
- **尚未完成**：Mac M2 + 14B 的速度與品質 `{待填}`；正確性由人確認；真實專案規模的驗證。

---

*出處連結集中定義於文件最後，供中英文兩部分共用。*

---

# English version

# Interview prep: on-prem codebase RAG

> **Language**: this section mirrors the Traditional Chinese section above, question by question; update both together.
> **Number rule**: every number comes from `docs/metrics.md`, `docs/decisions/`, `docs/devlog/` or `docs/evaluation/results/`; anything not measured stays `{待填}`. The "Sources" line under each answer is for checking while you review.
> **Three things to say up front** (better to volunteer them than to be caught on them):
> 1. All experiments ran on **Codespaces, 4 cores, CPU only, `qwen2.5-coder:3b`, `TOP_K=4`**, on the 20-file sample project, **one run per group**. Every Mac M2 + 14B number is still `{待填}`.
> 2. "Manual correctness" is **scored by AI (Claude)**; only the 5 least certain scores were re-checked by a person (conclusion unchanged); the rest are unconfirmed ([ADR 0018], [devlog 2026-11-05]).
> 3. Most of the code was written in Claude Code cloud sessions: about USD 7 for the first version, about USD 100 across all sessions so far ([metrics §1]).
> **Privacy**: every file name and symbol comes from `examples/sample-game-frontend/` or this repo.

---

## 1. Project pitch

### 30-second version

I built an **on-prem code Q&A system**. A team can ask a game front-end project, in Chinese, things like "where is the invincibility time configured?", and the system retrieves the relevant code and answers with `file:line` citations. The LLM (Ollama's `qwen2.5-coder`) and the vector database (Qdrant) run on our own machine, so **neither code nor questions leave it**. I also built automated evaluation and used 8 controlled experiment groups to decide which retrieval tricks deserve to be on. Only "split retrieval" earned a default-on recommendation; the other popular tricks (hybrid search, rerank, a similarity threshold and so on) were ruled out with data.

### 2-minute version

**Problem**: a game front-end project has roughly 50–300 files, and the question newcomers ask most is "where is X configured?". grep finds strings but cannot explain how things connect. A cloud AI assistant can, but the code cannot leave the company's machines, and the team needs a shared tool ([ADR 0001]).

**Architecture**: Ollama runs natively on the host (on a Mac, Docker cannot use the Metal GPU, [ADR 0002]); Qdrant, a FastAPI + LlamaIndex backend and a React frontend run in Docker. Indexing uses tree-sitter to chunk by function and class and Markdown by heading, so every citation maps to exact line numbers ([ADR 0004]), with incremental indexing keyed on content hashes. Answers stream over Server-Sent Events so that a proxy does not cut a connection that carries no data for a long time ([ADR 0010]).

**The two things I learned most from**:
- **Debugging**: on Codespaces, unit tests all passed and deployment still broke several times. The classic case was a query returning 504 at about 100 seconds: our own timeouts were 300 seconds, and bypassing the forwarder with `curl` made the same question succeed in 54.7 seconds, which located the problem in the Codespaces port forwarder ([ADR 0009], [ADR 0010]).
- **Experiments**: the first problem was that "where is the invincibility time configured?" retrieved 4 excerpts that were all Markdown. I built the evaluation tool first, then fixed the conditions and changed one switch at a time: hybrid retrieval, split retrieval, metadata, rerank, a similarity threshold and an anti-hallucination prompt. Split retrieval took the share of docs in the retrieved context from 95% to 25%, code-file retrieval from 1/9 to 6/9, and AI-scored correctness from 11 to 17 (out of 30). The usual 0.70 threshold would drop 93% of the correct excerpts. The anti-hallucination prompt refused 8 of the 9 answerable questions.

**Limits**: a 20-file sample project, one run per group, a 3B model on CPU, no Mac 14B measurement yet, and AI-scored correctness. I built the first version in one Claude Code session for about USD 7; I owned the architecture constraints, validation in real environments, and judging whether a hypothesis was right.

---

## 2. Twenty interview questions

> Format per question: **Question** → **Suggested answer** (spoken style, ready to say) → **Likely follow-up** (if any) → **Sources** (to check while reviewing).

### A. Architecture choices

#### Q1. Why on-prem instead of a cloud LLM API?

**Suggested answer**: three reasons. Privacy: source code is the most sensitive asset, so code and questions must not leave the company machine, and I did not want to review a third party's retention policy. Cost: usage is open-ended (many people, many questions), per-token billing is hard to predict, and the marginal cost on-prem is about electricity. And it is meant to be a shared team tool, not one subscription and one setup per person.

I am also clear about the price: a 14B local model is weaker than frontier cloud models at multi-step reasoning, so answer quality leans harder on retrieval quality, which is why I put so much into chunking and evaluation; throughput is one machine, so concurrent users queue; and the team owns operations (model updates, the Ollama process, disk).

**Likely follow-up**: how big is the quality gap? → Not measured yet. The 14B evaluation score on the Mac is `{待填}`; I only have 3B numbers from Codespaces. If quality is not enough, the ADR's plan is to test larger models on a GPU instance before reconsidering cloud APIs.

**Sources**: [ADR 0001] (alternatives: cloud API, cloud LLM + local vector DB, IDE assistant, grep), [metrics §5] (Mac and 14B cells are `{待填}`).

#### Q2. Why is Ollama not in Docker?

**Suggested answer**: Docker Desktop on a Mac runs containers in a Linux VM, and Apple's Metal GPU is not passed into that VM, so an Ollama in compose would be CPU-only on a Mac, and a 14B model would be unusably slow. Apple Silicon also has unified memory: memory given to the Docker VM is reserved for it, while a native process can use memory flexibly.

So the decision is that Ollama always runs natively on the host and containers call `host.docker.internal:11434`. The price is a two-part setup (install on the host, then compose) and platform differences; on Linux two more things are needed (`host-gateway` and `OLLAMA_HOST=0.0.0.0`, see Q15).

**Likely follow-up**: did you measure CPU against Metal? → Not yet. The ADR's follow-up is to record that number; today every Mac figure is `{待填}` and I will not make one up.

**Sources**: [ADR 0002] (alternatives: containerised Ollama, GPU passthrough, llama.cpp, LM Studio/MLX), [ADR 0006], [article 3], [metrics §3] (Mac cells `{待填}`).

#### Q3. Why Qdrant and not Chroma, pgvector or FAISS?

**Suggested answer**: the scale is tiny (a few thousand vectors at most), so performance is not the deciding factor; operational simplicity and features are. I needed similarity search that returns metadata (for citations), **deleting all chunks of one file**, **listing indexed files with their hash** (for incremental indexing), persistence in Docker, and unit tests that need no server. Qdrant's payload filters make delete-by-file direct, its in-memory mode keeps unit tests fast, and the built-in web dashboard helps debugging.

Chroma is simpler but has fewer filtering and operational features; pgvector needs a Postgres container and a schema; FAISS has no metadata or filtering; Milvus is far too heavy for a few thousand vectors.

**Likely follow-up**: any trouble? → Yes. LlamaIndex's `QdrantVectorStore` checks the collection's vector layout only in its constructor. The API process built its store before the index existed; the CLI indexer, a separate process, then created the collection, and the API kept querying a vector name that did not exist (`text-dense`), so every `/query` returned 502. Each unit test used a single store instance and missed it; the end-to-end run caught it.

**Sources**: [ADR 0003], [devlog 2026-10-30] (Problem 1, with the exact error message).

#### Q4. Why SSE streaming and not WebSocket, EventSource or polling?

**Suggested answer**: it started with the Codespaces 504. The original `/query` returned one JSON after the whole answer was generated, so during that minute not one byte went back to the browser; any proxy that drops connections without traffic will cut it, whatever timeouts we set. So I changed the shape of the request: a new `POST /query/stream` sends a heartbeat immediately, another every 10 seconds without output, then the citations (`sources`), `token` events as they are generated, and finally a `done` event with timings.

Not WebSocket: the traffic is one request → one stream, two-way adds nothing, it needs an `Upgrade` through every proxy, and it is harder to test with `curl`. Not `EventSource`: it supports only GET without a body, so the question would go into the URL and access logs, and its automatic reconnect would restart the whole generation. Polling an asynchronous job is the most thorough option, since every HTTP request stays short, but it needs new state and storage, so I kept it as the fallback.

**Likely follow-up**: did streaming really fix it? → Partly. In Codespaces, from the browser through the forwarded URL, one streamed query completed (time to first token 30.4 s, total 43.8 s, 129 tokens) with no 504. But 43.8 s is below the roughly 100 s at which the non-streaming version was cut, so it shows that streaming works there, **not** that the forwarder stopped limiting long queries; a query longer than 100 s has not been tested.

**Sources**: [ADR 0010] (with the alternatives table), [ADR 0009], [devlog 2026-11-02] (Problems 1, 2), [metrics §3].

### B. RAG fundamentals

#### Q5. Explain how embeddings and vector search work, and any details of your setup.

**Suggested answer**: at index time each chunk goes through an embedding model (`nomic-embed-text`, about 0.3 GB) and the vector is stored in Qdrant; at query time the question is embedded, the chunks with the highest cosine similarity are found, and the top `TOP_K` go into the prompt for the LLM.

Three details. First, `nomic-embed-text` needs prefixes: `search_document: ` for documents and `search_query: ` for questions. I hit a silent bug there: Compose passes an unset variable as an empty string, and pydantic treated `""` as "explicitly no prefix". No error, just worse retrieval; the fix treats an empty string as "auto", with a test. Second, the text sent to the embedding model has a header with the file path and symbol, while the stored text is the raw code, so citations show original lines. Third, collections are named per embedding model, so switching models is safe.

I also know one weakness: Chinese questions against an English-centric embedding model may retrieve worse than English questions. That risk is flagged in ADR 0005, and it is part of why Chinese docs always beat English code here (see Q13).

**Sources**: [ADR 0005] (embedding choice and risk), [ADR 0004], [devlog 2026-10-30] (Problem 2).

#### Q6. What is your chunking strategy, and why not fixed-size chunks?

**Suggested answer**: chunk by file type. TypeScript/JavaScript is parsed with **tree-sitter**: each top-level function, class, interface, type, enum or React component is one chunk, with its JSDoc; imports and other top-level statements form a `module` chunk; an oversized class is split per method; anything still too large is split into line windows with a 3-line overlap. Markdown is split by heading (ignoring `#` inside code fences), and each chunk records its heading path, such as "玩法規則 > 計分". The cap is `CHUNK_MAX_CHARS`, default 3000.

Why not fixed-size: it cuts functions in half, mixes unrelated functions in one chunk, and has no symbol names, while I need **exact line numbers** for citations (`src/entities/Player.ts:16-113`); a test checks that line numbers match the source. The 20-file sample project becomes 67 chunks.

The cost: it depends on pinned tree-sitter packages; small helpers become tiny chunks that use more `TOP_K` slots; and questions spanning many files (such as "list all components") remain a poor fit for chunk-level RAG.

**Likely follow-up**: what happens when chunking settings change? → `file_hash` covers the chunker version and `CHUNK_MAX_CHARS`, so files are re-chunked automatically; when `index_config` (including embedding settings) changes, a full rebuild runs by itself.

**Sources**: [ADR 0004], [ADR 0013] (settings fingerprint), [metrics §2] (20 files / 67 chunks).

#### Q7. What are hybrid retrieval and RRF, and what did you implement?

**Suggested answer**: vector search is good at meaning but weak on exact identifiers: `INVINCIBLE_MS` in a question is one token among many in embedding space. Hybrid retrieval runs several retrievers and merges their rankings. I built three channels: vector, BM25 keyword search, and "identifier-definition matching" (code-looking words in the question are matched case-sensitively against the names each chunk **declares**).

Merging uses **RRF (Reciprocal Rank Fusion)**: `score = Σ 1/(k + rank)` with `k=60`. It looks only at ranks, so cosine and BM25 scores never need a common scale, and a chunk found by several retrievers rises.

A trap I fell into: my first BM25 used character bigrams for Chinese, so every Chinese bigram of the question matched only the Chinese docs and outweighed the one exact identifier; the keyword channel amplified the docs-crowd-out-code problem. The fix: BM25 indexes only ASCII words, identifiers and numbers, and Chinese meaning is left to the vector channel. The price: a Chinese question with no identifier gives BM25 nothing to match.

**Sources**: [ADR 0013] (RRF, tokenizer, alternatives), [devlog 2026-11-02] (Problems 5, 6), [article 6].

#### Q8. What is rerank, and why is it not on by default?

**Suggested answer**: rerank feeds the (question, excerpt) pair together into a cross-encoder, which scores it more accurately than embedding cosine; it usually runs after retrieval to reorder the top N candidates. I made it optional: retrieve 10 candidates, rerank, keep `RERANK_TOP_N`, using `BAAI/bge-reranker-base` (278M; `v2-m3` is stronger, but takes 11.97 s for 10 pairs against 3.73 s).

Result: **on its own it does not help** (main-set defining file 0/3), because it can only reorder the 10 vector candidates, which for the main set are almost all Markdown, and a general-purpose reranker prefers docs: Markdown scored 0.8–0.99, code mostly below 0.1. Combined with hybrid and split retrieval (group I), the main-set defining file went 0/3 → 3/3, the best retrieval.

It is still off: each query pays +4.8 s of rerank, first token is about 10 s later than in group D (17.2 → 26.8 s), the image grows from 616 MB to 2.14 GB, and the code it promotes has rerank scores like 0.0027, a fragile ordering. Most importantly, AI-scored correctness is 17/30 for both I and C: better retrieval, not better answers.

**Sources**: [ADR 0015], [ADR 0018], [metrics §4a], [metrics §4b], [metrics §6] (image size).

#### Q9. Why was the similarity threshold not adopted?

**Suggested answer**: customer-support RAG commonly sets 0.70 and skips the LLM below it. I did not pick a value by feel; I wrote `calibrate_threshold.py`, which collects the cosine of every retrieved excerpt from the experiment reports and splits them into "from an expected file" and "from another file". The distributions almost overlap: expected excerpts have median **0.616** (n=27), others **0.604** (n=63). 0.70 would drop 25 of the 27 correct excerpts (**93%**) and leave 10 of 15 questions with none; 0.60, the only value that refuses the trick question, already leaves 6 real questions with no correct excerpt; values at or below 0.45 are safe and block nothing. The script's verdict was "no value suggested", so that group was never run.

The generic advice is not wrong; its premise (scores that separate relevance) does not hold for Chinese questions about an English codebase. Refusing a feature that does not exist needs a different signal. And a threshold is tied to the embedding model, so a new model needs a new calibration.

**Sources**: [ADR 0014], [calibration], [devlog 2026-11-03] (threshold calibration section), [article 6] (4.4).

### C. Experiment method

#### Q10. How did you design the experiments, and why do control groups and "one switch at a time" matter?

**Suggested answer**: evaluation tool first, then changes. Conditions are fixed (Codespaces, 4 cores, CPU, 3B, `TOP_K=4`, one warm-up question); every technique is an off-by-default `.env` switch; one switch changes per group; and after each change I check `/health` against the intended switches. Two question sets: a 10-question main set (phrased the way the team asks, mostly without identifiers) and a 5-question identifier set, because I expected keyword-style techniques to help only on the latter.

A concrete example of what a control group buys: with only A and B, I would have declared hybrid search effective (identifier-question defining file 33% → 100%). Adding C (split only) showed C alone is 3/3; adding D (hybrid + split) showed hybrid even pushed question 8 out on the main set (D 0/3 against C 1/3). Likewise, before D existed I credited I's gain to hybrid, and D reassigned it to rerank. **For every "it works", ask: with it removed, which other switch already does the job?**

Another trap is latency: group B's first token looked twice as fast (6.7 vs 13.0 s), but that was Ollama reusing a cached prompt; retrieval itself took only 0.07–0.21 s in every group.

**Sources**: [experiment plan] (fixed conditions, decision rule), [ADR 0012], [devlog 2026-11-03] (Problem 1, the Group D section), [metrics §4a], [article 6].

#### Q11. Explain refusal rate and false refusal rate, and why look at them together.

**Suggested answer**: the refusal rate is the share of trick questions (features the project does not have) answered "not found" without invented code; the false refusal rate is the share of **answerable** questions answered "not found". Looking only at the first fools you: prompt v3 added an explicit rule, "if no excerpt directly mentions this topic, reply only with a fixed sentence", and the refusal rate on the out-of-scope trick questions was **5/5**, with question 10 refused as well. But the next column of the same table shows false refusals of **8/9** answerable main-set questions, 2/5 on the identifier set and 3/3 on the control questions (features the project has but that are easy to mistake for missing). 19 of 23 answers were exactly the fixed sentence, including questions whose expected files had all been retrieved.

The decision rule was written before the run: the false refusal rate must stay 0 on every set, because a wrong "not found" hides code that exists, and one false refusal is worse than one more refused trick question. So v3 is not adopted. My hypothesis (untested) is that "directly mentions" is a judgement a 3B model does not make reliably; v3 has not been tried on 14B.

**Sources**: [ADR 0016], [metrics §4c], [devlog 2026-11-03] (Group J section).

#### Q12. What are the limits of your evaluation metrics?

**Suggested answer**: I wrote them into the decision in ADR 0012:
- **A keyword hit is not a correct answer.** The wrong Codespaces answer contained both `INVINCIBLE_MS` and 1500 while claiming the value is defined in `docs/gameplay.md`.
- **File recall measures what was retrieved, not what the model used.** In C and D, questions 7 and 9 retrieved an expected code file and the 3B model still answered from the wrong file.
- **The expected lists are mine**; a different chunk may also answer the question.
- **Refusal detection is a phrase match**, and it really had holes: the keyword list had only the Traditional 「無法」, so out-of-scope question 22's Simplified refusal 「我无法提供…」 scored "not refused", while questions 23 and 25 were invented answers that passed. The fix (ADR 0019) is a Traditional/Simplified list plus a check for files or symbols that do not exist in the project, with `--rescore` to re-score old reports without re-running the model. The check is still lexical and misses invented behaviour built from real names (29 of 59 answers scored 0 were flagged).
- **Correctness is AI-scored**, not human; only the 5 least certain scores were re-checked by a person.
- 10 questions is a small sample, run once; one question is noise.

That is why articles and resume say "automatic metrics only" or "AI-judged", and I never call keyword hit rate accuracy.

**Sources**: [ADR 0012] (Limitations), [ADR 0019], [ADR 0018] (Limits of the evidence), [devlog 2026-11-05].

#### Q13. So what is the conclusion, and how strong is the evidence?

**Suggested answer**: only **split retrieval** (`SPLIT_RETRIEVAL=true`, `DOC_TOP_K=1`) is on by default, and only in the Codespaces template `.env.codespaces` (ADR 0018); the Mac `.env.example` is unchanged until the Mac is measured. Evidence (main set, Codespaces 3B): docs among the retrieved chunks 95% → 25%, code-file retrieval 1/9 → 6/9, identifier-question defining file 1/3 → 3/3, retrieval time still 0.07–0.21 s; AI-scored correctness (both sets, out of 30) 11 → 17; and the doc-heavy questions 2, 3, 6 did not regress (0/2/2 → 0/2/2).

Why it works: docs share a language with the Chinese question and always beat English code in embedding space; instead of making code look more similar, guarantee code a seat.

I would be honest about the strength: the large effects (split against baseline, v3 last) are bigger than single-run noise, but the 16–17 point differences among B, C, D, F and I are not meaningful, since each group ran once and a 3B model words every answer differently. Question 2 (combo multiplier) is 0 in all 8 groups, a retrieval gap no switch closes.

**Sources**: [ADR 0018], [metrics §4a], [article 6] (4.2, 4.7).

### D. Debugging stories

#### Q14. Walk me through a layer-by-layer investigation: the 504 timeout.

**Suggested answer** (symptom → hypothesis → verification → conclusion):

- **Symptom**: in Codespaces, a question from the browser eventually showed 504.
- **Hypothesis 1**: one of our own timeouts is too short. **Verification**: list every hop's actual setting: nginx hard-coded to 900 s, the LLM timeout 600 s, the embedding call **with no timeout at all**. A 504 after about 1.5–2 minutes cannot come from the first two, so the hypothesis died. I still made every timeout configurable in `.env`, defaulting to 300 s, and made a timeout return a 504 naming the stage and the variable.
- **Turning point**: the cut-off stayed at **about 100 s**, matching none of 300, 600 or 900, which means another hop is giving up.
- **Hypothesis 2**: the Codespaces port forwarder in front of nginx. **Verification**: bypass it. `curl` straight to nginx inside the codespace succeeded in **54.7 s** for the same question; from the browser through the forwarded URL it returned 504 after about 100 s. The first path proved nginx, the backend and Ollama fine, leaving one layer.
- **Conclusion and fix**: I cannot change the forwarder's limit, but I can change the shape of the request, hence SSE streaming (Q4).

Two side stories: `curl -s` hides errors along with the progress bar, so I always use `-sS`; and my streaming test could never fail, because what actually held the stream back was gzip, not `proxy_buffering`, and the test's `curl` did not send `Accept-Encoding: gzip`, which hid it. I changed it to `curl --compressed` with a check that events arrive spread over time, and confirmed the test fails against a deliberately broken config.

**Sources**: [ADR 0009] ("before" settings table), [ADR 0010], [devlog 2026-11-01 Codespaces] (Problems 3, 5), [devlog 2026-11-02] (Problems 1, 2), [article 3].

#### Q15. Why does `host.docker.internal` not work on Linux, and how did you find out?

**Suggested answer**: the symptom was `/health` reporting Ollama unreachable while `curl localhost:11434` worked in the codespace terminal. The key idea: "I can reach it" and "the container can reach it" are different things; inside a container `localhost` is the container itself, and reaching the host goes through the Docker bridge gateway. So two suspects: name resolution and listen address.

Verify **from the caller's position**: run a throw-away container, `docker run --rm --add-host=host.docker.internal:host-gateway curlimages/curl -sS http://host.docker.internal:11434/api/version`, which sees the same network as the backend container. Then `ss -ltnp | grep 11434` shows where Ollama listens: by default `127.0.0.1`, so connections arriving over the bridge are refused.

Both causes get fixed: `extra_hosts: host.docker.internal:host-gateway` in compose (harmless on Docker Desktop, required on Linux) and starting Ollama with `OLLAMA_HOST=0.0.0.0`. A Mac never hits this because Docker Desktop resolves the name and forwards to the host's loopback.

Security note: `0.0.0.0` exposes 11434 on every interface and Ollama has no authentication, so `devcontainer.json` sets 11434 and 6333 to `ignore` (never forwarded), and on EC2 a security group blocks them.

**Sources**: [devlog 2026-11-01] (Problem 1), [devlog 2026-11-01 Codespaces] (Problems 3, 4), [ADR 0006], [ADR 0011], [article 3].

#### Q16. What was the Git LFS problem?

**Suggested answer**: in the codespace, `git push` was refused before anything was sent, although the repository does not use Git LFS (no `.gitattributes`, no LFS files). The message was `This repository is configured for Git LFS but 'git-lfs' was not found on your path…`.

Cause: the clone had Git LFS hooks in `.git/hooks/` (`pre-push` and friends, which call `git lfs …`), but the dev container's base image (`mcr.microsoft.com/devcontainers/base:ubuntu-24.04`) has no `git-lfs` binary and `post-create.sh` did not install it. The hook exits with an error without `git-lfs`, and a failing `pre-push` hook aborts the push.

Fix: `post-create.sh` installs `git-lfs` together with `jq`, `zstd` and `iproute2`, then runs `git lfs install --skip-repo`; without `--skip-repo`, existing hooks make it exit 2 (`Hook already exists: pre-push … run git lfs update --manual`), which would stop a `set -e` script and with it the whole `postCreateCommand`. `doctor.sh` got a check 12 that prints the install command (and the alternative of deleting the hook) when `git-lfs` is missing.

Lesson: an automated setup only contains what you have already tripped over, and each new kind of action (this time, push) can reveal a new gap.

**Sources**: [devlog 2026-11-03] (Problem 3), [ADR 0011], [article 3] (Bonus).

### E. Building with an AI coding agent

#### Q17. What did you do, and what did the AI do?

**Suggested answer**: the AI (a Claude Code cloud session) built the first version: backend, tree-sitter chunking, incremental indexing, API, React UI, Dockerfiles, compose, scripts, README, sample project and unit tests, in one session for about USD 7. Afterwards it turned my test log into fixes: configurable timeouts, CI, streaming, the dev container, `doctor.sh`, the evaluation scripts and experiment reports, with every decision written up as an ADR.

I did what the AI could not decide for me or could not see:
- **Architecture constraints**: Ollama not in Docker, code never leaving the machine, one compose file for every environment. Those are requirements.
- **Running it in real environments**: the cloud sandbox has no GPU, no real model, and is not Codespaces. I hit all three pitfalls in Codespaces myself, traced them layer by layer with `curl`, and handed them back as a test log. The AI fixes fast, but it cannot see an environment it has not run.
- **Judging whether a hypothesis is right**: a cut-off at 100 s rather than 300 s, a number that did not match, was the turning point.
- **Reviewing every PR and deciding which numbers may go into the docs**; anything not measured stays `{待填}`.

An honest addition: the later "manual correctness" is AI-scored, not mine, and that is the weakest link today. On cost: about USD 7 for the first version and about USD 100 across all sessions so far (the credit ran out).

**Sources**: [article 3] (section 5), [ADR 0001] (note), [metrics §1], [ADR 0018].

#### Q18. How do you verify what the AI produces?

**Suggested answer**: in four layers, each answering one question, cheapest first (ADR 0007): unit tests with fakes for logic (183 now, about 7 s, no network); compose and image checks; an end-to-end smoke test (real Ollama on the CI runner with a 0.5B model, which checks that the pipeline runs, not quality); and manual runs on the target environment. Quality is judged only on the target model and hardware, never on 0.5B or 3B alone.

Concrete examples:
- The AI ran an end-to-end test in its sandbox with a real Qdrant and a fake Ollama server, and caught the `text-dense` vector-name bug the unit tests missed (cross-process state, invisible to in-memory fakes).
- The streaming buffering problem: it first made the test fail against a deliberately broken nginx config to prove the test can catch it, then delivered the fix (`✗ All events arrived within 0.00s although the backend streamed for 4.321s.`).
- The experiments themselves: the evaluation script produces numbers, control groups correct conclusions, and limits go into ADRs; the script's own holes (Simplified refusals, invented answers) were found by reading the answers, then covered with tests and `--rescore`.

My rule: write verification results down as concrete records (symptom, command, error message, numbers) and hand those to the agent, with every number tagged with environment and source.

**Sources**: [ADR 0007], [ADR 0008], [devlog 2026-10-30] (Problem 1), [devlog 2026-11-02] (Problem 2), [ADR 0019], [metrics §6].

### F. If I started over, and limits

#### Q19. What would you do differently?

**Suggested answer**:
1. **Validate on the real target environments earlier.** The three deployment pitfalls were environment problems no unit test or CI run could catch; I would run the whole flow on a Linux rehearsal environment and on the Mac much sooner, instead of near the end. Every Mac number is still `{待填}`, the biggest gap.
2. **Build repeat runs and randomised order into the experiments from the start.** Each group ran once and the prompt cache disturbs latency (group B "twice as fast" is the example); I would run twice in alternating order to estimate noise.
3. **Plan manual scoring into the process from day one, done by a person.** Correctness is AI-scored now, and the last mile of the conclusions depends on confirming it.
4. **Record cost and data the same day.** Only the first version (about USD 7) and PR #3 (about USD 10) were recorded separately; the rest of the roughly USD 100 total is not itemised.
5. **Guard small processes**: two ADRs were both numbered 0016 (each took the "next free number" at the time) and had to be renamed; I would add a test that fails when two ADR files share a number.

**Sources**: [metrics §1], [metrics §2], [metrics §3], [devlog 2026-11-05] (Problem 1), [ADR 0018] (Follow-ups).

#### Q20. What are the current limits, and what is next?

**Suggested answer**:
- **Scale**: the sample project has 20 files and 67 chunks (3 of them Markdown); a real project has 50–300 files, where the candidate pool, BM25 behaviour and cosine distributions may differ, and a cap of one doc chunk may need re-checking.
- **Experiments**: one run per group, Codespaces, 4-core CPU, 3B, `TOP_K=4`, Chinese questions; the conclusions do not transfer automatically to the Mac, 14B or `TOP_K=8`.
- **Correctness**: AI-scored; the 5 least certain scores re-checked by a person, the rest unconfirmed.
- **A retrieval gap**: question 2 (combo multiplier) is 0 in all 8 groups, because the Chinese question has no identifier and no switch retrieves `ScoreSystem.ts`.
- **Evaluation**: the fabrication check is lexical and misses invented behaviour built from real names.
- **Product**: single-machine throughput; Simplified-character drift (a 3B model that a prompt does not hold; 2 answers still had it with v2).

Next (all in the ADR and devlog to-do lists): run `./scripts/benchmark-mac.sh` on the Mac and decide the Mac defaults separately (ADRs 0017, 0018); measure split + rerank without hybrid; try a Chinese → identifier glossary for the keyword channel; re-run the groups to estimate noise; have a person confirm the remaining scores; test a streaming query longer than 100 s and a codespace stop/start.

**Sources**: [ADR 0018] (Consequences, Follow-ups), [devlog 2026-11-05] (Next), [ADR 0019], [article 6] (sections 7, 8), [metrics §3].

---

## 3. One-page project summary (STAR)

> Ready to paste into a portfolio site. Every number comes from the repo; the environment is Codespaces, 4-core CPU, `qwen2.5-coder:3b`, `TOP_K=4`, the 20-file sample project, one run per experiment group; manual correctness is AI-scored.

### On-prem codebase RAG assistant

`Python` `FastAPI` `LlamaIndex` `Qdrant` `Ollama` `React` `Docker` `GitHub Actions` | [GitHub](https://github.com/alelcold/local-codebase-rag)

**Situation**
A game front-end team's project has roughly 50–300 files, and newcomers mostly ask "where is X configured?". grep finds strings but cannot explain how things connect; a cloud AI assistant can, but the source code must not leave the company's machines, and the team needs a shared tool.

**Task**
Build a complete RAG pipeline on one machine: ask in natural language (Chinese), get answers with `file:line` citations, with neither code nor questions leaving the machine. And decide with data, not intuition, which retrieval techniques deserve to be on.

**Action**
- **System**: Ollama runs natively on the host (for the Mac's Metal GPU); Qdrant, FastAPI + LlamaIndex and React run in Docker. Chunking uses tree-sitter per function/class and Markdown per heading, with incremental indexing on content hashes. Answers stream over SSE, getting around the Codespaces port forwarder cutting connections at about 100 s with a 504.
- **Operations**: one compose file for Mac, Codespaces and Linux GPU machines; a dev container that prepares Ollama, models, services and the index on every start; a 12-step `doctor.sh` that prints the fix for each failure; GitHub Actions CI with an end-to-end smoke test.
- **Experiments**: built automated evaluation first (`evaluate.py`; 10 + 5 + 8 questions), then fixed the conditions and changed one switch at a time across 8 controlled groups and 1 threshold calibration, and used the control groups to correct my own conclusion (hybrid search's apparent gain was already delivered by split retrieval).
- **AI collaboration**: built the first version in a Claude Code cloud session for about USD 7; I owned the architecture constraints, validation in real environments and judging hypotheses, and handed verification results back as concrete records.

**Result**
- **Split retrieval**: docs among the retrieved context 95% → 25%, code-file retrieval 1/9 → 6/9, identifier-question defining file 1/3 → 3/3, retrieval time still 0.07–0.21 s; AI-scored correctness 11 → 17 (out of 30). Applied to the Codespaces default settings (ADR 0018).
- **Six approaches ruled out by data**: hybrid search (nothing on top of split), chunk metadata and prompt v2 (no improvement), a similarity threshold (0.70 would drop 93% of correct excerpts), rerank (+4.8 s, about +10 s first token, image 616 MB → 2.14 GB, same 17/30 correctness as split), and the refusal prompt v3 (8 of 9 answerable questions refused).
- **Engineering**: a streamed query completes through the forwarded URL (time to first token 30.4 s, total 43.8 s); 183 unit tests in about 7 s with no network; the first version delivered in an AI session costing about USD 7.
- **Not done yet**: Mac M2 + 14B speed and quality `{待填}`; human confirmation of correctness; validation at real-project scale.

---

<!-- Reference links shared by the Chinese and English sections / 中英文共用的出處連結 -->

[ADR 0001]: ../decisions/0001-on-prem-rag-over-cloud-api.md
[ADR 0002]: ../decisions/0002-ollama-outside-docker-on-mac.md
[ADR 0003]: ../decisions/0003-qdrant-vector-database.md
[ADR 0004]: ../decisions/0004-chunking-by-file-type.md
[ADR 0005]: ../decisions/0005-model-selection-and-hardware.md
[ADR 0006]: ../decisions/0006-multi-environment-deployment.md
[ADR 0007]: ../decisions/0007-multi-environment-testing-strategy.md
[ADR 0008]: ../decisions/0008-ci-design.md
[ADR 0009]: ../decisions/0009-timeout-settings.md
[ADR 0010]: ../decisions/0010-streaming-responses.md
[ADR 0011]: ../decisions/0011-devcontainer-for-codespaces.md
[ADR 0012]: ../decisions/0012-automated-evaluation-metrics.md
[ADR 0013]: ../decisions/0013-hybrid-retrieval-and-split-retrieval.md
[ADR 0014]: ../decisions/0014-similarity-threshold.md
[ADR 0015]: ../decisions/0015-rerank.md
[ADR 0016]: ../decisions/0016-refuse-out-of-scope-questions-in-the-prompt.md
[ADR 0018]: ../decisions/0018-codespaces-default-retrieval-settings.md
[ADR 0019]: ../decisions/0019-refusal-scoring-simplified-and-fabrication-check.md
[devlog 2026-10-30]: ../devlog/2026-10-30.md
[devlog 2026-11-01]: ../devlog/2026-11-01.md
[devlog 2026-11-01 Codespaces]: ../devlog/2026-11-01-codespace-setup.md
[devlog 2026-11-02]: ../devlog/2026-11-02.md
[devlog 2026-11-03]: ../devlog/2026-11-03.md
[devlog 2026-11-05]: ../devlog/2026-11-05.md
[metrics §1]: ../metrics.md
[metrics §2]: ../metrics.md
[metrics §3]: ../metrics.md
[metrics §4a]: ../metrics.md
[metrics §4b]: ../metrics.md
[metrics §4c]: ../metrics.md
[metrics §5]: ../metrics.md
[metrics §6]: ../metrics.md
[experiment plan]: ../evaluation/experiment-plan-retrieval.md
[calibration]: ../evaluation/results/2026-11-03-threshold-calibration.md
[article 3]: articles/03-local-llm-deployment-pitfalls.zh-TW.md
[article 6]: articles/06-data-driven-rag-retrieval.zh-TW.md
