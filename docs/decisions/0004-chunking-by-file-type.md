# 0004. Chunking strategy by file type

- **Status**: Accepted
- **Date**: 2026-10-30
- **Related**: `backend/app/chunker.py`, `backend/tests/test_chunker.py`, [devlog 2026-10-30](../devlog/2026-10-30.md)

> English first; 繁體中文版本在下方.

## Context

Retrieval quality depends heavily on what a "chunk" is. For code Q&A:

- A chunk should be a **meaningful unit** (a function, a class, a doc section), so a retrieved chunk can answer "where/how does X work" on its own.
- Every chunk must keep **exact line numbers** for citations (`src/entities/Player.ts:16-113`).
- Chunks must fit the embedding model's context. `nomic-embed-text` handles about 2K tokens comfortably.
- The codebase is TypeScript/JavaScript (including JSX/TSX) plus Markdown docs.

## Decision

Chunk by file type, with `CHUNK_MAX_CHARS` (default 3000) as the upper bound:

| File type | Strategy |
| --- | --- |
| `.ts .tsx .js .jsx .mjs .cjs` | Parse with **tree-sitter**. Make one chunk per top-level function, class, interface, type, enum, or `const X = () => …` / `React.memo(...)` component. Leading JSDoc stays with its declaration. Imports and other top-level statements are grouped into a `module` chunk. An oversized class is split **per method**, and arrow-function fields count as methods. Anything still too large is split into line windows with a 3-line overlap. |
| `.md` | Split by heading, ignoring `#` inside fenced code. Each chunk records its heading path, e.g. `玩法規則 > 計分`. A heading with no body is merged into the next section. |
| Other configured extensions | Fixed line windows |

The text sent to the embedding model has a header with the file path and symbol, and nomic's `search_document:` prefix. The stored text is the raw code, so citations show the original lines. Each chunk's payload includes a `file_hash` that also covers the chunker version and `CHUNK_MAX_CHARS`, so changing chunking settings re-chunks files automatically.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| Fixed-size token/character windows (LlamaIndex default splitter) | Simple; language-agnostic | Cuts functions in half; a chunk often mixes two unrelated functions; weak symbol metadata | Lower retrieval precision for "where is X" questions |
| LlamaIndex `CodeSplitter` (tree-sitter) | Built in | Less control over JSDoc attachment, per-method splitting and line ranges; extra language-pack dependency | Needed exact line numbers and symbol names |
| Regex or brace-matching splitter | No native dependency | Fragile with JSX, template literals and strings | tree-sitter is robust and has wheels for arm64 |
| Whole file per chunk | Maximal context | Large files exceed the embedding context; similarity gets diluted | Bad for 300-line files |

## Consequences

- **Positive**: Chunks are natural answer units with symbol names (`Game.update`), which the UI and the LLM prompt both show. Line numbers are tested to match the source exactly.
- **Negative / trade-offs**:
  - It depends on tree-sitter grammar packages, which must be pinned.
  - Small helper functions become very small chunks. That is fine for retrieval, but it uses more `top_k` slots.
  - A question that spans many files (for example, "list all components") is still a poor fit for chunk-level RAG.
- **Follow-ups**: Use the evaluation set to tune `CHUNK_MAX_CHARS` and `TOP_K`. Consider adding the class header to method chunks as extra context.

---

# 0004. 依檔案類型切塊的策略

- **狀態**：已接受
- **日期**：2026-10-30

## 背景

檢索品質很大程度取決於「片段」怎麼切。對程式碼問答來說：

- 片段應該是**有意義的單位**（一個函式、一個 class、一個文件章節），取回的片段本身就能回答「X 在哪裡／怎麼運作」。
- 每個片段都必須保留**精確的行號**，以便引用（`src/entities/Player.ts:16-113`）。
- 片段要放得進 embedding 模型的上下文。`nomic-embed-text` 能輕鬆處理約 2K tokens。
- 專案是 TypeScript／JavaScript（含 JSX／TSX）加上 Markdown 文件。

## 決策

依檔案類型切塊，上限是 `CHUNK_MAX_CHARS`（預設 3000）：

| 檔案類型 | 策略 |
| --- | --- |
| `.ts .tsx .js .jsx .mjs .cjs` | 用 **tree-sitter** 解析。每個頂層 function、class、interface、type、enum，或 `const X = () => …`／`React.memo(...)` 元件各成一塊；上方的 JSDoc 跟著宣告。`import` 與其他頂層敘述合併成 `module` 片段。過大的 class **依 method 切開**（存放箭頭函式的欄位也算 method）。仍然太大的部分，再用重疊 3 行的行數視窗切開。 |
| `.md` | 依標題切開，忽略程式碼區塊中的 `#`。每塊記錄標題路徑，例如 `玩法規則 > 計分`。沒有內容的標題會併入下一個章節。 |
| 其他設定的副檔名 | 固定行數視窗 |

送進 embedding 模型的文字會加上檔案路徑與符號名稱的標頭，以及 nomic 的 `search_document:` 前綴；儲存的則是原始程式碼，所以引用顯示的是原本的程式碼行。每個片段的 payload 都有 `file_hash`，它同時涵蓋切塊器版本與 `CHUNK_MAX_CHARS`，所以修改切塊設定後，檔案會自動重新切塊。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| 固定大小的 token／字元視窗（LlamaIndex 預設） | 簡單；不分語言 | 會把函式切成兩半；常把兩個不相關的函式放在同一塊；符號資訊少 | 「X 在哪裡」這類問題的檢索精準度較差 |
| LlamaIndex `CodeSplitter`（tree-sitter） | 內建 | 較難控制 JSDoc 歸屬、依 method 切分與行號範圍；需要額外的語言套件 | 需要精確的行號與符號名稱 |
| 正規表示式或括號配對的切塊器 | 不需要原生套件 | 遇到 JSX、樣板字串、字串時容易出錯 | tree-sitter 較穩健，也有 arm64 wheel |
| 整個檔案當一塊 | 上下文最完整 | 大檔案會超過 embedding 上下文；相似度被稀釋 | 不適合 300 行的檔案 |

## 後果

- **正面**：片段就是自然的回答單位，並帶有符號名稱（`Game.update`），介面與 LLM 提示詞都會顯示。行號與原始碼完全一致，並有測試保證。
- **負面／取捨**：
  - 依賴 tree-sitter 的語法套件，必須固定版本。
  - 小型輔助函式會變成很小的片段。這對檢索沒問題，但會多占用 `top_k` 的名額。
  - 跨很多檔案的問題（例如「列出所有元件」）仍然不適合片段層級的 RAG。
- **後續工作**：用評估題組調整 `CHUNK_MAX_CHARS` 與 `TOP_K`。考慮在 method 片段加上 class 標頭作為額外上下文。
