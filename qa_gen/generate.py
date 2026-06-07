# -*- coding: utf-8 -*-
"""问题清洗 + LLM 生成单条 QA + 负样本构造。"""
import re

from qa_gen.config import _stats, log_event, DOC_NAME, MAX_RETRIES_PER_ITEM
from qa_gen.data_io import _norm
from qa_gen.gold import find_supporting_chunk, fill_gold_ids
from qa_gen.llm_client import gen
from qa_gen.buckets import SYS_PROMPT, NEG_BUCKETS


def clean_question(q):
    """问题清洗：删除中英文括号及括号内内容；保证只在末尾保留一个问号。"""
    if not q:
        return q
    q = re.sub(r"[（(][^）)]*[）)]", "", q)
    q = q.replace("?", "？")
    if q.count("？") >= 2:
        parts = q.split("？")
        head = "、".join(p for p in parts[:-1] if p != "")
        tail = parts[-1]
        q = head + "？" + (tail if tail else "")
    q = re.sub(r"、+", "、", q)
    q = re.sub(r"\s{2,}", " ", q).strip()
    return q


def build_user_prompt(task, chunks_for_task):
    parts = [
        f"任务：{task['hint']}",
        f"答案类型倾向：{task['answer_type']}（single_fact / multi_chunk / table_lookup）",
        f"问题分类：{task['category']}（A 列固定为该值）",
        f"意图：{task['intent']}（I 列固定为该值）",
        "",
        "可用 chunk（content 已与原 jsonl 一致，注意字形）：",
    ]
    for c in chunks_for_task:
        page = c.get("page_start") or "（无）"
        parts.append(f"### chunk_id = {c['chunk_id']} | section = {c['section_title']} | page = {page} | type = {c['chunk_type']}")
        parts.append(c.get("content") or "")
        parts.append("")
    parts.append("请针对【任务】写 1 条 QA，严格按系统要求输出 JSON。")
    return "\n".join(parts)


def gen_one_qa(task, by_id, all_chunks):
    chunks_for_task = [by_id[cid] for cid in task["chunk_ids"] if cid in by_id]
    if not chunks_for_task:
        log_event(f"[SKIP] 任务 {task['key']} 找不到 chunk_ids，跳过。")
        return None
    user_prompt = build_user_prompt(task, chunks_for_task)
    last_err = None
    for attempt in range(MAX_RETRIES_PER_ITEM + 1):
        out = gen([
            {"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": user_prompt},
        ])
        if not isinstance(out, dict):
            last_err = "LLM 返回非 dict"
            _stats["retries"] += int(attempt > 0)
            continue
        q = (out.get("question") or "").strip()
        a = (out.get("answer") or "").strip()
        st = (out.get("supporting_text") or "").strip()
        pcid = (out.get("primary_chunk_id") or "").strip()
        # 写出前先清洗 question：去括号 + 多问号合并
        q = clean_question(q)
        if not (q and a and st):
            last_err = "字段缺失"
            _stats["retries"] += int(attempt > 0)
            continue
        # 校验：question < 50 字、简体；这里不强转，直接长度检查
        if len(q) > 50:
            last_err = f"question 太长 ({len(q)})"
            _stats["retries"] += int(attempt > 0)
            continue
        # 校验：supporting_text 是否为某 candidate chunk 的子串
        primary_id = find_supporting_chunk(st, chunks_for_task)
        if not primary_id:
            last_err = f"supporting_text 不是任一 chunk 的子串"
            _stats["retries"] += int(attempt > 0)
            continue
        # 用 LLM 报告的 primary_chunk_id 兜底（如有效则优先）
        if pcid in [c["chunk_id"] for c in chunks_for_task]:
            # 但仍要求 supporting_text 是该 chunk 的子串
            if _norm(st) in _norm(by_id[pcid].get("content") or ""):
                primary_id = pcid
        page = by_id[primary_id].get("page_start")
        # 回填 G 列：F 子串匹配（不再用关键词灌水）
        gold_ids = fill_gold_ids(st, primary_id, all_chunks)
        # 收紧后若只剩 1 个 chunk，但任务声明 multi_chunk，则回退为 single_fact
        effective_atype = task["answer_type"]
        if len(gold_ids) <= 1 and effective_atype == "multi_chunk":
            effective_atype = "single_fact"
        return {
            "category": task["category"],
            "question": q,
            "answer": a,
            "document": DOC_NAME,
            "page": page if page is not None else "",
            "supporting_text": st,
            "gold_chunk_ids": ";".join(gold_ids),
            "answer_type": effective_atype,
            "intent": task["intent"],
            "primary_chunk_id": primary_id,
            "section_title": by_id[primary_id]["section_title"],
            "task_key": task["key"],
        }
    log_event(f"[DROP] 任务 {task['key']} 重试 {MAX_RETRIES_PER_ITEM} 次仍失败：{last_err}")
    _stats["dropped"] += 1
    return None


def gen_negatives():
    """直接构造负样本：按规格 §10 示例，不需要调 LLM。"""
    rows = []
    for nb in NEG_BUCKETS:
        rows.append({
            "category": "产品",
            "question": clean_question(nb["question"]),
            "answer": "該產品彩頁未提供該信息，無法從本文檔回答。",
            "document": DOC_NAME,
            "page": "",
            "supporting_text": "",
            "gold_chunk_ids": "",
            "answer_type": "unanswerable",
            "intent": "拒答",
            "primary_chunk_id": "",
            "section_title": "[NEGATIVE]",
            "task_key": nb["key"],
        })
    return rows
