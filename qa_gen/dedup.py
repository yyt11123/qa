# -*- coding: utf-8 -*-
"""embedding 语义去重（同 section_title 桶内）。"""
from collections import defaultdict

from qa_gen.config import log_event, DEDUP_SIM_THRESHOLD
from qa_gen.gold import cos_sim_matrix
from qa_gen.llm_client import embed


# -------- 语义去重（embedding） --------
def dedup_by_embedding(rows):
    """同 section_title 桶内 cos>=0.85 视为重复，保留信息更全（answer 更长）的一条。"""
    answerable = [r for r in rows if r["answer_type"] != "unanswerable"]
    if not answerable:
        return rows
    # 把所有 question 一起向量化（≤1 批，因为 ≤40 条）
    texts = [r["question"] for r in answerable]
    vecs = embed(texts)
    if vecs is None:
        log_event("[WARN] embedding 失败，跳过语义去重。")
        return rows
    sim = cos_sim_matrix(vecs)
    # 按 section_title 桶内做两两比较
    bucket = defaultdict(list)
    for i, r in enumerate(answerable):
        bucket[r["section_title"]].append(i)
    drop = set()
    for sec, idxs in bucket.items():
        for ii in range(len(idxs)):
            for jj in range(ii + 1, len(idxs)):
                a, b = idxs[ii], idxs[jj]
                if a in drop or b in drop:
                    continue
                if sim[a, b] >= DEDUP_SIM_THRESHOLD:
                    # 保留 answer 更长的（信息更全）；若一样长保留较短 question
                    if len(answerable[a]["answer"]) >= len(answerable[b]["answer"]):
                        drop.add(b)
                    else:
                        drop.add(a)
    if drop:
        log_event(f"[DEDUP] 同 section 内 cos≥{DEDUP_SIM_THRESHOLD} 删除 {len(drop)} 条。")
    kept_answerable = [r for i, r in enumerate(answerable) if i not in drop]
    negatives = [r for r in rows if r["answer_type"] == "unanswerable"]
    return kept_answerable + negatives
