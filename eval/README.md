# RAG Evaluation

This folder contains a lightweight manual evaluation workflow for ZhiYu RAG.

## What The User Fills In

Edit `rag_testset.jsonl`. Each line is one test case:

```json
{"id":"case-001","question":"你的问题","top_k":5,"expected_answer_points":["答案应该提到的点"],"acceptable_answer_terms":["可接受的同义表达"],"negative_case":false,"expected_sources":["应该命中的文献名或关键词"],"must_retrieve_terms":["检索片段里应该出现的关键词"]}
```

Field notes:

- `expected_answer_points`: preferred answer points to match.
- `acceptable_answer_terms`: alternate wording that should also count as correct.
- `min_answer_hits`: minimum number of hits required to pass a complex summary question.
- `negative_case`: set to `true` when the correct behavior is "the document does not clearly say this".

Start with 10-20 high-value questions. Good questions include:

- Fact questions: the answer should be directly in the document.
- Summary questions: the answer should combine several chunks.
- Citation questions: the answer must cite the right article/page/section.
- Negative questions: the document does not contain enough evidence.

## Run Retrieve-Only Evaluation

```powershell
python eval/run_rag_eval.py --api-base https://yyxu123-zhiyu-api.hf.space
```

## Run Retrieve + Chat Evaluation

```powershell
python eval/run_rag_eval.py --api-base https://yyxu123-zhiyu-api.hf.space --with-chat
```

Reports are written to `eval/runs/`.

Files produced per run:

- `rag_eval_...json`: full machine-readable results.
- `rag_eval_...md`: full long-form report.
- `rag_eval_..._summary.md`: compact overview and failure list.
- `rag_eval_..._summary.csv`: spreadsheet-friendly summary table.

## How To Read Results

- `source_hit`: whether retrieved chunks include the expected source hints.
- `term_hit`: whether retrieved chunks include the expected key terms.
- `required_answer_hits`: the pass threshold for the current case.
- `answer_pass`: whether the answer passed the current rule set.
- `top_similarity`: the first result score returned by the backend.
- `human_score`: left blank for manual scoring.

Practical note:

- If `source_hit` is `False` but the top source is clearly the right article, first check whether `expected_sources` is too strict before treating it as a retrieval failure.

Use the report to mark each case:

- `2`: good answer and good source.
- `1`: partially correct.
- `0`: wrong, missing, or unsupported.
