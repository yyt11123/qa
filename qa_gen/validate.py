# -*- coding: utf-8 -*-
"""§9 校验。"""
from qa_gen.config import DOC_NAME
from qa_gen.data_io import _norm
from qa_gen.generate import clean_question


# -------- 校验 §9 --------
def validate_rows(rows, by_id, all_chunks):
    issues = []
    short_count = 0
    for idx, r in enumerate(rows):
        if r["answer_type"] == "unanswerable":
            if r["gold_chunk_ids"]:
                issues.append((idx, "unanswerable 行 G 列应为空"))
            continue
        # G 列 chunk 都存在
        gids = [g for g in r["gold_chunk_ids"].split(";") if g]
        for g in gids:
            if g not in by_id:
                issues.append((idx, f"gold chunk_id 不存在：{g}"))
        # F 列必须是某 gold chunk 的子串
        f_ok = False
        for g in gids:
            if _norm(r["supporting_text"]) in _norm(by_id[g].get("content") or ""):
                f_ok = True
                break
        if not f_ok:
            issues.append((idx, "F 列不是任一 gold chunk 的子串"))
        # document 名
        if r["document"] != DOC_NAME:
            issues.append((idx, f"document 列错：{r['document']}"))
        # question 长度 / 简体 / 一题一问（粗略）
        if len(r["question"]) > 50:
            issues.append((idx, f"question 超过 50 字：{len(r['question'])}"))
        if len(r["question"]) < 30:
            short_count += 1
        # 一题一问：清洗后应只剩末尾 1 个问号；含括号视为不合格
        cleaned = clean_question(r["question"])
        if cleaned != r["question"]:
            issues.append((idx, "question 含括号或多问号（应已被 clean_question 处理）"))
        if (cleaned.count("？") + cleaned.count("?")) > 1:
            issues.append((idx, "question 含多个问号（清洗后仍 >1）"))
    # ≥90% 短问
    answerable_n = sum(1 for r in rows if r["answer_type"] != "unanswerable")
    short_ratio = short_count / max(1, answerable_n)
    return issues, short_ratio
