# I tried a pile of "industry standard" RAG retrieval tricks and kept exactly one switch

> **Status**: draft, not published. `[Screenshot: …]` and `[Chart: …]` mark where a figure should go; `{待填}` marks numbers not measured yet.
> **Language**: English version. The Traditional Chinese version is [`06-data-driven-rag-retrieval.zh-TW.md`](06-data-driven-rag-retrieval.zh-TW.md). The two match section by section; update both together (a documented exception to the bilingual rule, see [`../article-series.md`](../article-series.md)).
> **Important limitation**: retrieval and latency numbers are automatic metrics. Correctness scores (section 4.7) were judged by **AI (Claude), not a person**; a person re-checked only the 5 least certain ones. Everything was measured on a 20-file sample project, one run per group, with a 3B model on CPU.
> **Plan**: Article 6 in [`../article-series.md`](../article-series.md). Sources: [devlog 2026-11-02](../../devlog/2026-11-02.md), [devlog 2026-11-03](../../devlog/2026-11-03.md), [`metrics.md`](../../metrics.md) §4a / §4b / §4c, the [experiment plan](../../evaluation/experiment-plan-retrieval.md), the [threshold calibration output](../../evaluation/results/2026-11-03-threshold-calibration.md), ADRs [0012](../../decisions/0012-automated-evaluation-metrics.md), [0013](../../decisions/0013-hybrid-retrieval-and-split-retrieval.md), [0014](../../decisions/0014-similarity-threshold.md), [0015](../../decisions/0015-rerank.md), [0016](../../decisions/0016-refuse-out-of-scope-questions-in-the-prompt.md), [0018](../../decisions/0018-codespaces-default-retrieval-settings.md) and PR #20 (correctness scoring).
> **Privacy**: every file name, symbol and question comes from `examples/sample-game-frontend/` or this repo.

## TL;DR

- Asked "Where is the invincibility time after the player gets hit configured?", my on-prem codebase RAG retrieved 4 excerpts that were **all Markdown**. `src/config/gameConfig.ts`, which defines the constant, was not among them.
- I built the evaluation tool first (`evaluate.py`: a 10-question main set, a 5-question identifier set and an 8-question out-of-scope set), then tried 7 approaches in turn: hybrid retrieval, split retrieval, chunk metadata, prompt v2, a similarity threshold, rerank and an anti-hallucination prompt v3. Conditions were fixed (Codespaces, CPU, 3B model, `TOP_K=4`) and one switch changed at a time.
- Result: **only split retrieval (`SPLIT_RETRIEVAL`) earns a default-on recommendation.** Docs among the retrieved chunks went from 95% to 25%, code-file retrieval from 1/9 to 6/9, and retrieval time stayed at 0.07–0.21 s. The other six stay off by default: hybrid adds nothing on top of split; metadata and prompt v2 did not help; the usual 0.70 similarity threshold would drop 93% of the correct excerpts; rerank costs +4.8 s and about +10 s to first token; prompt v3 falsely refuses 8 of 9 answerable questions.
- The biggest lesson is not which trick works. It is that **looking at group B (hybrid) alone made it look very effective, until a control group D showed that split retrieval had already done the job.**
- Correctness scoring (by AI, 5 least certain re-checked by a person) agrees: split retrieval takes correct answers from 11 to 17 of 30. The rerank setup I scores the same 17 and costs about 10 s more per query, and question 2 scores 0 in all 8 groups because the right file is never retrieved. **Better retrieval did not always mean better answers.**
- **All of this was measured on a 20-file sample project, one run per group, with a 3B model on CPU, and most correctness scores are unconfirmed by a person.**

---

## 1. Starting point: the answer was wrong because all 4 excerpts were docs

The sample project has a typical newcomer question: "Where is the invincibility time after the player gets hit configured?" A good answer points to `INVINCIBLE_MS = 1500` in `src/config/gameConfig.ts`, and to where `src/entities/Player.ts` uses it.

In Codespaces (`qwen2.5-coder:3b`, `TOP_K=4`) I asked this from the browser. Streaming worked fine (time to first token 30.4 s, total 43.8 s), but the 4 citations were:

```text
引用的檔案：[1] README.md:26-32 [2] docs/gameplay.md:10-14 [3] docs/architecture.md:1-9 [4] docs/architecture.md:11-20
玩家受傷後的無敵時間是在 `docs/gameplay.md` 文件的第 10 行到第 14 行設定的。…
```

[Screenshot: the UI showing 4 citations, all .md, with the answer saying the invincibility time is defined in docs/gameplay.md]

Two different problems are hiding in that answer:

1. **A retrieval problem**: all 4 excerpts were documentation and none was the defining code. The model could only quote the docs, so it said the value is "defined in `docs/gameplay.md`".
2. **A generation problem**: the answer drifted into Simplified Chinese (具体来说, 代码, 无, 时间, 定义).

(Note that this answer contains the word `INVINCIBLE_MS` and still points to the wrong file. A keyword hit is not a correct answer, which is the subject of the next section.)

My first guess: a Chinese question sits closer to Chinese docs than to English code in embedding space, and the 4 slots of `TOP_K=4` fill up with docs. **That was a guess and I had not verified it.** So the next step was not to tune anything. It was to be able to measure.

---

## 2. Build the evaluation tool before changing anything

Changing retrieval without numbers gets you "the one question I asked looks better now". I wrote `scripts/evaluate.py` (ADR 0012) before touching anything.

### Metric design

The script asks every question through `/query/stream` (the same path as the UI) and records, per question:

| Metric | How | Why |
| --- | --- | --- |
| Defining file retrieved (locate-the-setting questions) | Is a `definition_files` **code** file among the retrieved excerpts? | For "where is X configured", docs that merely mention X do not count |
| Code file / doc file retrieved | Expected files among the retrieved, split by extension (`.md` = doc) | Shows docs crowding out code directly |
| Doc share of retrieved chunks | Share of retrieved chunks that are `.md` | A bias signal that does not depend on the expected list |
| Answer cites an expected file | `[n]` in the answer mapped to sources | Whether the model uses the right excerpt |
| Keyword hit rate | Case-insensitive substring match; any alternative counts | Rough check that key facts appear |
| Simplified characters | 200 Simplified-only characters, with zero false positives on this repo's Traditional docs | Language drift of small models |
| Refusal (trick question) | A refusal phrase and no forbidden keyword (`WebSocket`…) | Hallucination resistance |
| Time to first token, total time | Measured in the client from the request | Speed as the user feels it |

On top of that, **manual correctness** (0–2 per question) is an empty column a person fills in, then `--apply-manual` writes it back. The automatic numbers are never called "accuracy".

### What these metrics cannot tell you (written into ADR 0012)

- **A keyword hit is not a correct answer.** The wrong answer from section 1 contains both `INVINCIBLE_MS` and 1500 and still names the wrong file.
- **File recall measures what was retrieved, not what was used.** The model can ignore a retrieved file or cite the wrong one.
- **The expected lists are mine.** A different chunk may also answer the question; a miss is a prompt to look, not proof of failure.
- **Refusal detection is a phrase match.** That one really does bite later (section 6).
- 10 questions is a small sample; a difference of one question is noise.

That is why this article keeps repeating it: today's numbers are a **screening signal**, not answer quality.

### An early lesson: the same question twice

Asking the same question twice took time to first token from 30.4 s to 0.8 s, because Ollama reused the cached prompt. So the script always asks 10 **different** questions after one unscored warm-up and never repeats a question. In section 4.1 the cache fools me once more anyway.

---

## 3. Experiment design

### Fixed conditions

| Item | Value |
| --- | --- |
| Environment | GitHub Codespaces, 4 cores / 16 GB, CPU only |
| Models | `qwen2.5-coder:3b`, `nomic-embed-text` |
| `TOP_K` / `LLM_NUM_CTX` | 4 / 8192 |
| Sample project | 20 files, 67 chunks |
| Warm-up | on (one unscored question per run) |
| Runs per group | **one** |

### One switch at a time

Every technique is an `.env` switch, all off by default (ADR 0013). For each group I overrode them with shell variables, checked `/health` against the intended switches, then ran the evaluation. Every run finished with 0 errors (devlog 2026-11-03).

### Two question sets

- **Main set** (`questions.yaml`, 10 questions): phrased the way the team asks, mostly with **no identifier**. Question 1 does not say `INVINCIBLE_MS`. Types: locate-the-setting 3, explain-logic 3, cross-file flow 3, trick question 1.
- **Identifier set** (`questions-identifiers.yaml`, 5 questions): the question names an identifier, for example "Where is `INVINCIBLE_MS` defined?".

I split them because I expected keyword-style techniques to help only when the question contains an identifier. That turned out to be right, for a cleaner reason than I thought (section 4.1).

### Groups

| Group | Switches | Question it answers |
| --- | --- | --- |
| A baseline | all off | Reference numbers |
| B hybrid | `HYBRID_SEARCH` | Does keyword + identifier matching bring the defining code in? |
| C split | `SPLIT_RETRIEVAL`, `DOC_TOP_K=1` | Does capping docs stop them crowding out code? |
| D hybrid + split | B + C | Do they add up? |
| E metadata alone | `CHUNK_METADATA` | **Not run** (optional; folded into F) |
| F all on | B + C + `CHUNK_METADATA` + `PROMPT_VARIANT=v2` | The full package |
| G threshold | `SCORE_THRESHOLD` | **Not adopted after calibration, not run** (section 4.4) |
| H rerank | `RERANK`, 10 → 4 | Can a cross-encoder put the defining code into the top 4? |
| I hybrid + split + rerank | B + C + `RERANK` | What does rerank add on top of D? |
| J D + prompt v3 | `PROMPT_VARIANT=v3` | Does an explicit "not found" rule make a 3B model refuse features that do not exist? |

There are 10 group labels, and 8 groups were actually run (A, B, C, D, F, H, I, J); G was calibrated only and E was skipped. D was skipped at first too and run later, and running it changed my conclusions about both B and I.

---

## 4. The experiments, one by one

Each section follows "expectation → result → why". Results are automatic metrics; correctness (AI-judged) is added in the overview and in section 4.7.

### The overview first

[Chart: bar chart per group A → J of "defining file retrieved (main)", "code file retrieved" and "doc share"]

| Group | Defining file, main | Defining file, ident. | Code file, main | Docs among retrieved chunks, main | Correctness (AI), main / ident. |
| --- | --- | --- | --- | --- | --- |
| A baseline | 0/3 | 1/3 | 1/9 | 95% | 5 / 6 |
| B + hybrid | 0/3 | 3/3 | 3/9 | 88% | 9 / 7 |
| C + split | 1/3 | 3/3 | 6/9 | 25% | 7 / 10 |
| D hybrid + split | 0/3 | 3/3 | 6/9 | 25% | 7 / 9 |
| F all on (+ metadata, v2) | 0/3 | 3/3 | 5/9 | 25% | 6 / 10 |
| H + rerank | 0/3 | 2/3 | 2/9 | 85% | 6 / 8 |
| I D + rerank | 3/3 | 3/3 | 7/9 | 23% | 8 / 9 |
| J D + prompt v3 | 0/3 | 3/3 | 6/9 | 25% | 3 / 5 |

Source: metrics §4a. One run per cell. Correctness is out of 20 (main) and 10 (ident.), judged by AI.

### 4.1 Hybrid retrieval (B)

**Expectation**: the question contains `INVINCIBLE_MS`, yet vector search gets pulled toward the Chinese docs. Adding BM25 plus "identifier-definition matching" (merged with RRF) should bring in `gameConfig.ts`, which declares it.

**Result (looking at B alone)**: on the identifier set, defining-file retrieval went from **1/3 to 3/3 (33% → 100%)**, the doc share from 60% to 30%, at a few milliseconds of retrieval time. It looks like a big win.

The main set barely moved: defining file 0/3 → 0/3, code file 1/9 → 3/9, doc share 95% → 88%.

**Why the main set did not move**: I saw this while building it. My first BM25 used character bigrams for Chinese. Querying "玩家受傷後的無敵時間在哪裡設定？INVINCIBLE_MS 是多久？" ranked:

```text
45.5  README.md            Starlight Courier（範例專案） > 可以試著問的問題
19.7  docs/gameplay.md     玩法規則 > 生命與受傷
 9.9  src/entities/Player.ts
 8.7  src/config/gameConfig.ts
```

The docs are Chinese and the code is not, so every Chinese bigram of the question (無敵, 敵時, 時間, 設定…) matched only docs and outweighed the one exact identifier. **The keyword channel was amplifying the problem I wanted to fix.** The fix was to index only ASCII words, identifiers and numbers in BM25 and leave Chinese meaning to the vector channel. The price: **main-set questions have no identifier, so BM25 has nothing to match.** In B, 7 of the 10 main questions retrieved exactly the same excerpts as in A.

**A latency trap**: B's mean time to first token was 6.7 s against A's 13.0 s, which looks twice as fast. But retrieval took only 0.07–0.21 s in every group, so hybrid search cannot save that much. Question by question, 2, 4 and 9 got their first token in about 0.2 s; those three retrieved the same excerpts as in A, so the prompt was identical and Ollama reused its cache. The questions whose excerpts changed (5 and 8) were not faster (11.7 → 13.9 s, 16.2 → 15.0 s). **So B's latency must not be read as an improvement.**

**Conclusion from B alone (later corrected)**: hybrid retrieval is very effective; identifier questions went from 1/3 to 3/3.

**After the control group D**: C (split only) is **also 3/3** on the identifier set. The 33% → 100% gain did not need BM25 at all. It is worse on the main set:

- Questions 1 and 9: D retrieved exactly the same excerpts as C (vector channel only; a Chinese question gives BM25 nothing).
- Question 8 (`InputManager.ts`): C retrieved it (vector channel). In D, RRF ranked candidates found by both vector and keyword (`Player.ts`, `Hud.tsx`, `Game.ts`) above it, so **hybrid search pushed it out**. Defining file retrieved: C 1/3, D 0/3.

**Conclusion**: hybrid adds nothing on top of split, and on the main set it once pushed an expected file out. It helps only when the question names an identifier and there is no split retrieval, at a cost of milliseconds. Stays optional and off by default.

If I had stopped after A and B, I would have put hybrid search into the defaults.

### 4.2 Split retrieval (C)

**Expectation**: docs are close to Chinese questions in embedding space. Capping docs at `DOC_TOP_K=1` of the retrieved slots and giving the rest to code should bring code files in.

**Result** (main set, automatic metrics only):

| Metric | A | C |
| --- | --- | --- |
| Docs among retrieved chunks | 95% | **25%** (exactly the `DOC_TOP_K=1` cap) |
| Code file retrieved | 1/9 | **6/9** |
| Defining file retrieved, main | 0/3 | 1/3 (question 8) |
| Defining file retrieved, ident. | 1/3 | **3/3** |
| Retrieval time | 0.07–0.21 s (every group) | same |

**Why it works**: it does not change which excerpt looks more similar, only how the slots are allocated. Docs share a language with the question and always beat English code; instead of trying to make code look more similar, guarantee code a seat. That is also why it costs almost nothing: it allocates among 30 candidates and needs no extra model call.

**What it did not fix**:
- Question 1 (`gameConfig.ts`, invincibility time) is **still missed** in C. Main-set defining file is only 1/3.
- More Simplified-character answers: 3 in C against 1 in A. My hypothesis (**untested**): with mostly code in the prompt, the 3B model drifts to Simplified more often.
- Longer time to first token (15.9 s against A's 13.0 s) because the retrieved code excerpts are longer than doc sections (for example 146 lines for question 3 → 47 s). Latency comparisons are unreliable because of the cache effect (4.1), so this is "it looks like".

**The risk I checked**: with docs capped at 1, questions whose point is in the docs (2, 3 and 6) might have gotten worse. They did not: 0 / 2 / 2 in the baseline, 0 / 2 / 2 in C (AI-judged, section 4.7).

**Conclusion**: the best return on cost in the whole experiment, and **the only switch turned on by default** (`.env.codespaces`, ADR 0018). Questions 2, 3 and 6 did not regress.

### 4.3 Chunk metadata and prompt v2 (F)

**Expectation**: putting a "Defines: … INVINCIBLE_MS" header into the embedded text should let 無敵 match `INVINCIBLE`; prompt v2 (always Traditional Chinese, file and line numbers first) should suppress Simplified characters.

**Result** (F = B + C + metadata + v2, compared with C):

| Metric | C | F |
| --- | --- | --- |
| Defining file retrieved, main | 1/3 | **0/3** |
| Code file retrieved, main | 6/9 | 5/9 |
| Answer cites an expected file (`[n]`), main | 1/9 | 4/9 |
| Answers with Simplified, main | 3 | 2 |
| Mean answer tokens | 109 | 241 |
| Total time, mean, main | 25.7 s | 42.8 s |

**Why it did not help**:
- Question 1 still misses `gameConfig.ts`: the header did not make 無敵 match `INVINCIBLE` for `nomic-embed-text`.
- F also lost C's hit on question 8, because metadata changes the embedding of every code chunk.
- v2 makes answers longer and starts them with `[n] path:lines` lists, which lifts "cites an expected file" from 1/9 to 4/9. **That is a format change, not a retrieval improvement**; whether the answers are more correct is for manual scoring.
- Simplified characters still appear in 2 answers (`体`, `冲`). A prompt alone does not hold a 3B model.

**Conclusion**: no improvement, stays off. It also has a hidden cost: changing `CHUNK_METADATA` forces a full re-index (18.8–20.7 s).

### 4.4 Similarity threshold (G): the customer-support-RAG 0.70 does not work here

**Expectation**: the trick question ("How does online multiplayer sync player positions?", a feature the sample project does not have) should retrieve low-scoring excerpts. Set a threshold; below it, skip the LLM and answer "not found". 0.70 is a common choice in customer-support RAG.

**Method**: I did not pick a value by feel. `calibrate_threshold.py` collects the cosine scores of every retrieved excerpt from the A and C reports (main + identifier sets), splits them into "from an expected file", "from another file" and "from the trick question", and lists how many correct excerpts each candidate threshold would drop.

**Result: the distributions almost overlap**

| Excerpts | n | Median | Range |
| --- | --- | --- | --- |
| Expected file (correct) | 27 | **0.616** | 0.487–0.745 |
| Other file (not relevant) | 63 | **0.604** | 0.466–0.759 |
| Trick question | 7 | 0.542 | 0.478–0.570 |

| Threshold | Correct excerpts dropped | Other excerpts blocked | Questions losing every expected excerpt | Trick refused |
| --- | --- | --- | --- | --- |
| ≤ 0.45 | 0/27 | 0/70 | 0 | 0/1 |
| 0.50 | 2/27 (7%) | 10/70 (14%) | 0 | 0/1 |
| 0.55 | 4/27 (15%) | 18/70 (26%) | 2 | 0/1 |
| 0.60 | 13/27 (48%) | 36/70 (51%) | 6 | 1/1 |
| **0.70** | **25/27 (93%)** | 69/70 (99%) | **10** | 1/1 |

(The data comes from the main and identifier sets of groups A and C, 15 questions; the denominator for "other excerpts blocked" is 70 because the 7 trick-question excerpts count as non-expected.)

**Why**: the median cosine of correct excerpts is 0.616 and of irrelevant excerpts 0.604, a gap of 0.012. The cosine score **does not tell you whether an excerpt is relevant**. A threshold of 0.70 drops 25 of the 27 correct excerpts (93%) and leaves 10 of 15 questions with no correct excerpt. The only value that refuses the trick question, 0.60, already leaves 6 real questions with no correct excerpt. Values at or below 0.45 are safe and block nothing.

The calibration script's verdict is "**no value suggested**", so group G was never run and `SCORE_THRESHOLD` stays empty.

One more limit: the metadata index (F) cannot be calibrated either, because F's reports were written before `vector_score` existed and hold no cosine scores. And the threshold is tied to the embedding model; a new model needs a new calibration.

[Chart: cosine distribution of expected vs. irrelevant excerpts (box plot), with 0.70 marked]

**Conclusion**: not adopted. Refusing the trick question needs a different signal.

### 4.5 Rerank (H, I)

**Expectation**: a cross-encoder sees the (question, excerpt) pair together and should be more accurate than embedding cosine, so it should rank the defining code into the top 4.

**On its own (H)**: it does not help.

| Metric | A | H |
| --- | --- | --- |
| Defining file, main / ident. | 0/3 / 1/3 | 0/3 / 2/3 |
| Code file retrieved, main | 1/9 | 2/9 |
| Doc share, main | 95% | 85% |
| Rerank time (mean) | — | 2.9 s (main) / 4.4 s (ident.) |
| Time to first token, mean, main | 13.0 s | 21.2 s |

**Why**: rerank can only reorder the **10 vector candidates**, and for the main set those are almost all Markdown, so there is no code to choose from. A general-purpose reranker also prefers docs: Markdown excerpts scored 0.8–0.99, code excerpts mostly below 0.1. B and C, which change *which* candidates exist, reach 3/3 on the identifier set; H reaches 2/3.

**Combined with split and hybrid (I = D + rerank)**:

| Metric | D | I |
| --- | --- | --- |
| Defining file retrieved, main | **0/3** | **3/3** |
| Code file retrieved, main | 6/9 | 7/9 |
| Answers with Simplified, main / ident. | 4 / 2 | 0 / 0 |
| Rerank time (main) | — | 4.8 s (2.4–6.7) |
| Time to first token, mean, main | 17.2 s | 26.8 s (**+9.6 s**) |

The main set's defining files are finally all retrieved: question 1's `gameConfig.ts` comes first, question 8 gets `InputManager.ts` and question 9 `GameState.ts`. This time question 1's answer names `src/config/gameConfig.ts`, `INVINCIBLE_MS` and 1500 ms (keyword check only; correctness still to be judged).

**But**:
- **The scores are tiny.** Question 1's `gameConfig.ts` got a rerank score of 0.0027 against 0.0003 for the next code excerpt; question 8's got 0.0738 against 0.0003–0.03. The ordering is fragile, and the gain is 3 questions from one run each.
- **The cost.** Rerank takes 4.8 s per query (code chunks are longer than doc sections, hence more than H's 2.9 s); time to first token D → I is about 10 s more (17.2 → 26.8 s); the backend image grows from 616 MB to 2.14 GB (+1.5 GB). The reranker micro-benchmark: `bge-reranker-base` 3.73 s for 10 pairs, against `bge-reranker-v2-m3` at 11.97 s (4 vCPU cloud container, not a Codespace).
- **On the identifier set rerank adds nothing**: C, D and I are all 3/3, and "cites an expected file" even falls from 4/5 to 2/5.
- **Rerank scores do not separate the trick question either.** In I, question 10's best score was 0.33, while real question 9's best was only 0.0165.
- One control is still missing: **C + rerank (no hybrid)**. D already shows hybrid does nothing on the main set, so that combination may give I's result at the same rerank cost. Worth one run before choosing between D and I as a default.

**I credited the wrong thing at first**: before group D existed, I attributed question 8's hit to hybrid search. Only after running D did it show that question 8 was already retrieved in C (pure vector), that hybrid pushed it out, and that rerank brought it back. That comparison is also where section 4.1 comes from.

**Conclusion**: off by default. It is the best main-set retrieval so far, but it costs 4.8 s of rerank, about 10 s of first-token time and 1.5 GB of image, and the gain rests on scores of 0.003–0.07.

### 4.6 Anti-hallucination prompt v3 (J): refuse the trick questions, and the real ones with them

**Expectation**: the 3B model invents answers for trick questions (no group A–I refused question 10). An explicit rule in the prompt, "if no excerpt directly mentions this topic, reply only with a fixed 'not found' sentence", should make it refuse them.

**Method**: J = D + prompt v3. I also built an out-of-scope set (8 questions: trick questions 21–25, and control questions 26–28, which are features the project **does** have but that are easy to mistake for missing, such as saving, sound and window focus loss) and ran D (prompt v1) on it first as the reference. J retrieved **exactly the same excerpts** as D on all 23 questions, so every difference comes from the prompt.

**Result**:

| Metric | D (v1) | J (v3) |
| --- | --- | --- |
| Trick questions refused, out-of-scope 21–25 | 2/5 (keyword screen, re-scored under ADR 0019; it was 1/5) | **5/5** |
| Question 10 refused | No | **Yes** |
| False refusal, control 26–28 | 0/3 | **3/3** |
| False refusal, main (9 answerable) | 0/9 | **8/9** |
| False refusal, ident. | 0/5 | **2/5** |
| Answers that are only the fixed sentence | 0/23 | **19/23** |
| Keyword hit rate, main / ident. | 28% / 83% | 18% / 48% |

**Why**: 19 of J's 23 answers are, word for word, 「在索引的專案中找不到相關內容。」 (11 tokens). v3 did not tell real questions from trick questions; it pushed the model toward the shortest, safest output. The refused real questions include ones where **every expected file had been retrieved** (main question 5, 2/2; on identifier questions 11 and 13 the identifiers `INVINCIBLE_MS` and `DASH_COOLDOWN_MS` appear verbatim in a retrieved excerpt). My hypothesis (**untested**): "if no excerpt *directly* mentions this topic" is a judgement the 3B model does not make reliably, and that reminder is the last thing it reads before `## Answer`.

One more detail: time to first token did not drop (20.3 s against 17.2 s, though that difference is noisy from the cache), because the model still reads the whole prompt before writing the refusal. Total time dropped by about 3 s only because the answers are short.

**Conclusion**: not adopted. The experiment plan wrote the decision rule down before I ran anything: **the false refusal rate must stay 0 on every set**, because a wrong "not found" hides code that exists, and one false refusal is worse than one more refused trick question. v3 has not been tried on 14B (Mac); the failure may be specific to 3B.

---

### 4.7 Does better retrieval mean better answers? Correctness scores

**How it was scored**: all 136 answers (8 groups × 15 questions, plus 16 out-of-scope answers) were read against the sample project's source and given 0 (wrong or invented), 1 (partly right) or 2 (all key facts right). They were shuffled per question with no group name, so the same standard applies to every group. **The scoring is by AI (Claude), not a person.** A person re-checked the 5 least certain scores and the conclusions did not change; the other scores are unconfirmed.

| Group | Main (/20) | Ident. (/10) | Total (/30) |
| --- | --- | --- | --- |
| A baseline | 5 | 6 | 11 |
| B + hybrid | 9 ¹ | 7 | 16 |
| **C + split** | **7** | **10** | **17** |
| D hybrid + split | 7 | 9 | 16 |
| F all on (+ metadata, v2) | 6 | 10 | 16 |
| H + rerank | 6 | 8 | 14 |
| **I D + rerank** | **8** | 9 | **17** |
| J D + prompt v3 | 3 | 5 | 8 |

¹ B's first place on the main set rests on three answers scored 1 that could be 0; with 0 it is 6, below C.

Three things the scores say:

1. **C = I = 17 of 30, but I costs about 10 s more per query.** I has rerank (+4.8 s) on top of D, and its first token is 26.8 s against D's 17.2 s, plus a 2.15 GB image. It gains questions 1 and 9 over C and loses 3 and 8. Paying that for no more correct answers is a bad trade, so rerank stays off.
2. **Question 2 (combo multiplier) is 0 in all 8 groups, and that is a retrieval gap, not a switch effect.** In no group did the top 4 contain `ScoreSystem.ts` or `gameConfig.ts`, and the Chinese question has no identifier (`COMBO_STEP`) for the keyword channel to catch. With nothing relevant in front of it, the 3B model invents a `Player.ts` combo with the wrong numbers. No switch in this article fixes it; a Chinese → identifier glossary is the next thing to try.
3. **Better retrieval does not mean better answers.** I retrieves best (defining file 3/3, code 7/9, keyword hit 45%) and scores only 1 point more than C on the main set and 1 less on the identifier set. In C and D, questions 7 and 9 stay 0 although an expected code file was retrieved: the 3B model answers from the wrong file (`Player.ts`, `Hud`, `UiStore.score`) instead of the excerpt. Retrieval metrics tell you what the model was shown, not whether it read it.

The check I was waiting for: split retrieval did not hurt the questions whose point is in the docs. Questions 2 / 3 / 6 score 0 / 2 / 2 in the baseline and 0 / 2 / 2 in C.

**Caveat**: one run per group, and a 3B model that words every answer differently (C and D have different answer text on all 10 main questions and the same total). One point is noise; only the large gaps (split against baseline, v3 last) are safe to read.

## 5. Final defaults

The recommendation in [devlog 2026-11-03](../../devlog/2026-11-03.md), confirmed by the correctness scores and **applied to `.env.codespaces`** ([ADR 0018](../../decisions/0018-codespaces-default-retrieval-settings.md)). `.env.example` (Mac) is unchanged:

| Switch | Recommendation (Codespaces, 3B, CPU, `TOP_K=4`) | Reason |
| --- | --- | --- |
| `SPLIT_RETRIEVAL=true`, `DOC_TOP_K=1` | **On** (applied; no drop on questions 2, 3 and 6) | Biggest gain for milliseconds: code file 1/9 → 6/9, docs 95% → 25%, ident. defining file 1/3 → 3/3 |
| `HYBRID_SEARCH` | Keep off (optional) | Nothing on top of split; pushed out question 8 on the main set (D 0/3 vs C 1/3); costs milliseconds |
| `RERANK` | Keep off | Best retrieval (I: defining file 3/3) but +4.8 s, about +10 s to first token and +1.5 GB of image, and the gain rests on scores of 0.003–0.07; C + rerank not run yet |
| `CHUNK_METADATA` | Keep off | F: no gain, and it lost C's question 8 hit; changing it forces a full re-index |
| `SCORE_THRESHOLD` | Leave empty | No value can be calibrated (correct 0.616 vs. irrelevant 0.604) |
| `PROMPT_VARIANT` | Keep `v1` | v2: no retrieval gain, Simplified still 2; v3: main-set false refusals 8/9 |
| `QUERY_GLOSSARY` | Keep off (implemented, not yet tested) | Only an offline check so far (3/19 → 16/19, an upper bound); the end-to-end group K is {待填}; needs `HYBRID_SEARCH` (ADR 0020) |

The plan's own decision rule says: "turn a switch on by default when it improves defining file retrieved or manual correctness and does not lower manual correctness on any question type; write a new ADR for the change of defaults." Split retrieval meets it (correctness 11 → 17 of 30, no drop on questions 2, 3 and 6), and the change of defaults is recorded in ADR 0018, together with the reasons each other switch stays off and the limits of the evidence.

The Mac `.env.example` (14B, `TOP_K=8`) is unchanged and waits for `./scripts/benchmark-mac.sh`: `DOC_TOP_K` with `TOP_K=8` is untested.

---

## 6. What I learned

1. **A control group matters more than any single result.** With only A and B, I would have declared hybrid retrieval effective, with identifier questions going from 1/3 to 3/3. Adding C showed C alone does it; adding D showed hybrid even pushes a question out on the main set. Likewise, I credited I's gain to hybrid until D reassigned it to rerank. **For every "it works", ask: with it removed, which other switch already does the job?**
2. **Look at the refusal rate and the false refusal rate together.** v3's 5/5 refusal rate is lovely; the false refusal rate in the next column of the same table is 8/9. Report only the first and it is a successful experiment.
3. **Validate generic advice on your own data.** 0.70 is common in customer-support RAG; on this data it drops 93% of the correct excerpts, because the cosine distributions of correct and irrelevant excerpts overlap. The general-purpose reranker gives docs 0.8–0.99 and code mostly below 0.1. The advice is not wrong; its premises (docs and question in different languages from code, scores that separate relevance) do not hold for "Chinese questions about an English codebase".
4. **The evaluation script has holes too.**
   - The trick-question refusal keywords originally listed 「無法」 in Traditional form only, not the Simplified 「无法」. Out-of-scope question 22's answer, 「我无法提供…」, is a refusal written in Simplified, and it scored "not refused". ADR 0019 replaced the per-question copies with one Traditional/Simplified list and re-scored the old reports.
   - Questions 23 (cloud sync "via `syncUi`") and 25 (gamepad mapped to the keyboard handler) are **invented answers** that pass the "not refused, no forbidden word" check. Reading D's answers, it refused 2 of 5; the keyword screen counted 1 before the fix and counts 2 after it. Invented behaviour built from real names is still not caught by the fabrication check that ADR 0019 added (it checks that files and symbols exist).
   - On the other side, question 28's 「没有直接处理…的逻辑」 is a wrong answer, but a bare 「没有」 is deliberately not a refusal phrase, so it is not counted as a false refusal.
   - None of this touches J's numbers (its refusals are the exact fixed sentence), but it does affect the control group D.
5. **Latency numbers fool you easily.** B's "twice as fast" was the prompt cache; asking the same question twice differs by 40×. Compare latency between groups with care, and do not credit it to the technique.
6. **Rebuild the backend image after merging backend code.** When I ran J, the backend would not start (`PROMPT_VARIANT must be one of ['v1', 'v2'], got 'v3'`) because the image had been built for H and I, before the v3 code. That failure was loud; a change that does not fail at startup would not have been noticed.
7. **Better retrieval does not mean better answers.** Rerank gave the best retrieval of the whole experiment and the same 17 correct-answer points as the cheapest switch. A retrieval metric measures what the model was shown, not what it did with it; keep a correctness column next to it, and keep it from the start.

---

## 7. Limits

- **A 20-file, 67-chunk sample project.** A real project has 50–300 files; the candidate pool, BM25 behaviour and cosine distributions may differ.
- **One run per group.** A difference of one question is noise, and there are no repeat runs to estimate variance.
- **A 3B model on CPU** (`qwen2.5-coder:3b`, `TOP_K=4`, 4 cores). Production is 14B on a Mac M2 with `TOP_K=8`; v3 may behave differently on 14B. That gap has not been measured.
- **Correctness is AI-judged.** Claude scored the answers; a person re-checked only the 5 least certain (conclusion unchanged). Scoring was lenient where the main mechanism was right and a secondary fact missing. A keyword hit rate is still not accuracy.
- **Both question sets are mine**, and so are the expected-file lists.
- Simplified-character detection uses a conservative 200-character list and only catches clear drift.
- Latency is affected by the prompt cache and by run order, and was not measured repeatedly.

---

## 8. Next steps

- [x] **Correctness scoring**: done by AI with the 5 least certain re-checked by a person; C did not hurt questions 2, 3 and 6; defaults recorded in ADR 0018. Still open: a person confirming the other scores.
- [ ] **Mac 14B**: run `./scripts/benchmark-mac.sh --with-rerank` and record the results in metrics; also check whether v3 still refuses almost everything on 14B, and `DOC_TOP_K` with `TOP_K=8`.
- [ ] **Group K: a Chinese term → identifier glossary**: BM25 indexes ASCII only, so a Chinese question gives it nothing. `QUERY_GLOSSARY` (ADR 0020) maps Chinese terms in the question to identifiers; it is implemented and off by default, and **has no end-to-end experiment yet** (group K, {待填}). An offline check (keyword and identifier channels only, glossary written by someone who had seen the questions, so an upper bound) raised the expected code files in the top 4 from 3/19 to 16/19, including `gameConfig.ts` for question 1 and `ScoreSystem.ts` for question 2. Question 1 was missed in every group except I.
- [ ] **C + rerank**: check whether, without hybrid, the same rerank cost gives I's main-set result.
- [x] Fix the evaluation script's Simplified refusals and add a fabrication check, then re-score old reports: done (ADR 0019); D's out-of-scope refusal rate re-scores to 2/5.
- [ ] If refusal is retried: a v4 prompt without the trailing reminder, or a rule tied to something checkable (the question's identifier or file is in no excerpt).

Source code, ADRs, devlogs and every evaluation report are in the repo: https://github.com/alelcold/local-codebase-rag

---

## Appendix A: title options

1. I tried 6 "industry standard" RAG retrieval tricks and kept exactly one switch
2. The customer-support-RAG 0.70 threshold would drop 93% of the correct excerpts in my codebase RAG
3. One experiment group almost gave me the wrong conclusion: using control groups to test RAG retrieval tricks

## Appendix B: LinkedIn summary (about 150 words)

Asked where the invincibility time is configured, my on-prem codebase RAG retrieved four excerpts, all Markdown, and none of them the code that defines it. I built an evaluation tool first, then fixed the conditions and changed one switch at a time: hybrid search, rerank, a similarity threshold, a metadata header and an anti-hallucination prompt. Only split code/doc retrieval earned a default-on recommendation: docs among retrieved chunks 95% to 25%, code-file retrieval 1/9 to 6/9, at about 0.1 s. The usual 0.70 threshold would drop 93% of correct excerpts, and the refusal prompt falsely refused 8 of 9 answerable questions. A control group also overturned my first conclusion about hybrid search. Scoring the answers agreed: split retrieval took correct answers from 11 to 17 of 30, the same as a rerank setup that costs 10 s more, and better retrieval did not always mean better answers. Caveats: answers scored by AI, 20-file sample project, one run per group, 3B model on CPU.

## Publishing checklist

- [ ] Every path, symbol and screenshot comes from `examples/sample-game-frontend/` or this repo.
- [ ] Every number is checked against `docs/metrics.md` §4a / §4b / §4c, devlog 2026-11-02 / 03 and the evaluation reports, with its environment stated (Codespaces, CPU, 3B, `TOP_K=4`, one run per group).
- [x] Correctness scores are in (sections 4.7 and 5) and no conclusion was contradicted.
- [ ] Say in the published text that the correctness scores are AI-judged, unless a person has confirmed the rest by then.
- [ ] Fill in every `[Screenshot: …]`, `[Chart: …]` and `{待填}`.
- [ ] Keep the Chinese version in sync with any change.
- [ ] After cross-posting, add the links back to `article-series.md`.
