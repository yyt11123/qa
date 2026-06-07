# -*- coding: utf-8 -*-
"""F 列子串定位、关键短语抽取、G 列回填、余弦相似度矩阵。"""
import re

import numpy as np

from qa_gen.data_io import _norm


def find_supporting_chunk(supporting_text, candidate_chunks):
    """返回 supporting_text 是其 content 子串的第一个 chunk_id；找不到返回 None。"""
    target = _norm(supporting_text)
    if not target:
        return None
    for c in candidate_chunks:
        if target in _norm(c.get("content") or ""):
            return c["chunk_id"]
    return None


# -------- 关键短语提取与 G 列回填 --------
def extract_keyphrases(text):
    """从 answer/supporting_text 抽取关键短语：数字+量词、百分比、显式数字。"""
    if not text:
        return []
    phrases = set()
    for m in re.findall(r"\d{1,4}(?:,\d{3})*(?:\.\d+)?\s*(?:%|％|港元|美元|澳門幣|個月|個|个月|个|歲|岁|次|年|天|日|份|港币|美金|港|公里|周|週)", text):
        phrases.add(m.strip())
    for m in re.findall(r"\d{1,4}(?:,\d{3})*(?:\.\d+)?\s*[%％]", text):
        phrases.add(m.strip())
    # 中文数字+量词的稳健形式
    for m in re.findall(r"\d{1,4}\s*[次年月日歲岁个個%％]", text):
        phrases.add(m.strip())
    # 关键中文短语
    for kw in ["最多索償", "最多索偿", "最多", "等候期", "保額", "保额", "保單貨幣", "投保", "繳付", "缴付", "額外保障", "終期紅利", "现金价值"]:
        if kw in text:
            phrases.add(kw)
    return [p for p in phrases if len(p) >= 1]


def fill_gold_ids(supporting_text, primary_id, all_chunks):
    """G 列：保留所有 content（空白归一化后）包含 supporting_text 的 chunk。
    必须含 primary_id；排除 doc_summary（除非它就是 primary）；按 chunk_index 排序。"""
    nf = _norm(supporting_text)
    hits = []
    if nf:
        for c in all_chunks:
            if (c["chunk_type"] == "doc_summary") and (c["chunk_id"] != primary_id):
                continue
            if nf in _norm(c.get("content") or ""):
                hits.append(c)
    ids = {c["chunk_id"] for c in hits}
    ids.add(primary_id)
    idx_of = {c["chunk_id"]: c["chunk_index"] for c in all_chunks}
    return sorted(ids, key=lambda cid: idx_of.get(cid, 9999))


# -------- 余弦相似度 --------
def cos_sim_matrix(vecs):
    m = np.array(vecs, dtype=np.float32)
    norm = np.linalg.norm(m, axis=1, keepdims=True) + 1e-12
    m = m / norm
    return m @ m.T
