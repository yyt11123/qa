# -*- coding: utf-8 -*-
"""自动桶生成器：扫描 JSONL → 筛选 QA 级 chunk → 生成 task dict → 负样本。

与 gen_one_qa 接口兼容，生成的结果可直接送入 generate.py 的流水线。
"""

import json
import random
from collections import defaultdict

from qa_gen.auto_config import (
    INTENT_MAP,
    CATEGORY_MAP,
    DEFAULT_CATEGORY,
    NEGATIVE_TEMPLATES,
    NEGATIVE_COUNT,
    MAX_CHUNKS_PER_SECTION,
    MIN_CONTENT_LENGTH,
    EXCLUDED_CHUNK_TYPES,
)
from qa_gen.config import log_event


# ── chunk 筛选 ──

def _is_qa_worthy(chunk: dict) -> bool:
    """判断一个 chunk 是否适合出题。"""
    if chunk.get("chunk_type", "") in EXCLUDED_CHUNK_TYPES:
        return False
    content = (chunk.get("content") or "").strip()
    if len(content) < MIN_CONTENT_LENGTH:
        return False
    return True


def _select_chunks(chunks: list[dict], max_total: int = 30) -> list[dict]:
    """从 JSONL 的所有 chunk 中选出 QA 级 chunk，控制总量和分布。"""
    worthy = [c for c in chunks if _is_qa_worthy(c)]

    # 按 section_title 分组，每组最多取 MAX_CHUNKS_PER_SECTION
    by_section = defaultdict(list)
    for c in worthy:
        sec = c.get("section_title") or "_no_section_"
        by_section[sec].append(c)

    selected = []
    for sec, chs in by_section.items():
        # 每组内按 chunk_index 排序，均匀采样
        chs.sort(key=lambda c: c.get("chunk_index", 0))
        if len(chs) <= MAX_CHUNKS_PER_SECTION:
            selected.extend(chs)
        else:
            # 均匀采 MAX_CHUNKS_PER_SECTION 个
            step = len(chs) / MAX_CHUNKS_PER_SECTION
            for i in range(MAX_CHUNKS_PER_SECTION):
                idx = int(i * step)
                selected.append(chs[idx])

    # 按 chunk_index 全局排序，取前 max_total
    selected.sort(key=lambda c: c.get("chunk_index", 0))
    if len(selected) > max_total:
        # 均匀采样而非截断，避免只取文档前半部分
        step = len(selected) / max_total
        sampled = []
        for i in range(max_total):
            idx = int(i * step)
            sampled.append(selected[idx])
        selected = sampled

    return selected


# ── task 构建 ──

def _build_hint(chunk: dict, intent: str) -> str:
    """从 chunk 内容自动生成 hint：section_title + 内容前若干字的摘要。

    这给 LLM 一个出题方向，不替代 LLM 自己的判断。
    实际出题时 LLM 会看到完整 chunk content。
    """
    sec = (chunk.get("section_title") or "").strip()
    content = (chunk.get("content") or "").strip()
    chunk_type = chunk.get("chunk_type", "")
    content_type = chunk.get("content_type", "")

    # intent → 方向关键词
    intent_hints = {
        "查详情": "介绍/说明",
        "要数字": "具体数字/比例",
        "查覆盖": "覆盖范围/包含哪些",
        "资格门槛": "条件/门槛/要求",
        "查核保": "核保要求/条件",
        "操作指引": "操作步骤/流程",
        "问优惠": "优惠/折扣/活动",
        "缴费": "缴费方式/金额",
        "理赔": "理赔流程/时效",
    }
    direction = intent_hints.get(intent, "")

    # table 类 chunk：用 section_title + 表格标题就够了，不摘取单元格原文
    if chunk_type == "table_row" or content_type == "table":
        caption = (chunk.get("table_caption") or "").strip()
        if caption:
            hint = f"{sec} - {caption}"
        else:
            hint = sec
        if direction:
            hint = f"[{direction}] {hint}"
        return hint[:120]

    # prose / leaf 类 chunk：取首句
    first_sent = ""
    for ch in content[:100]:
        first_sent += ch
        if ch in "。；\n" and len(first_sent) >= 15:
            break

    # 去掉表格管道符（有些表格内容被当 prose 存储）
    if first_sent.strip().startswith("|"):
        first_sent = first_sent.replace("|", "").strip()
        # 取第一个有意义的片段
        parts = [p.strip() for p in first_sent.split("  ") if len(p.strip()) >= 2]
        first_sent = parts[0] if parts else first_sent

    if sec and first_sent:
        hint = f"{sec}：{first_sent}"
    elif sec:
        hint = sec
    else:
        hint = first_sent

    if direction and direction not in hint:
        hint = f"[{direction}] {hint}"

    return hint[:120]


def _pick_answer_type(chunk: dict, doc_type: str) -> str:
    """根据 chunk 类型和文档类型推断 answer_type。"""
    ct = chunk.get("chunk_type", "")
    if ct == "table_row":
        return "table_lookup"
    if ct == "section_summary":
        # 如果 section_summary 包含子节点引用，适合 multi_chunk
        children = chunk.get("children_ids") or []
        if len(children) >= 2:
            return "multi_chunk"
        return "single_fact"
    return "single_fact"


def _pick_category(doc_type: str) -> str:
    """根据 doc_type 确定 category。"""
    return CATEGORY_MAP.get(doc_type, DEFAULT_CATEGORY)


def _pick_intent(doc_type: str, index: int) -> str:
    """按 doc_type 对应的 intent 列表轮转选取。"""
    intents = INTENT_MAP.get(doc_type, ["查详情"])
    return intents[index % len(intents)]


def build_task_from_chunk(
    chunk: dict,
    doc_type: str,
    product_name: str,
    index: int,
) -> dict:
    """从单个 chunk 构建一个 task dict（与 gen_one_qa 兼容）。

    task dict 格式：
      {key, intent, category, answer_type, chunk_ids, hint, product_name}
    """
    intent = _pick_intent(doc_type, index)
    answer_type = _pick_answer_type(chunk, doc_type)
    category = _pick_category(doc_type)
    hint = _build_hint(chunk, intent)
    cid = chunk["chunk_id"]

    return {
        "key": f"auto_{cid}",
        "intent": intent,
        "category": category,
        "answer_type": answer_type,
        "chunk_ids": [cid],
        "hint": hint,
        "product_name": product_name,
    }


def build_auto_negatives(doc_type: str, product_name: str) -> list[dict]:
    """按 doc_type 自动生成负样本（unanswerable 题）。"""
    templates = NEGATIVE_TEMPLATES.get(doc_type, NEGATIVE_TEMPLATES["other"])
    chosen = random.sample(templates, min(NEGATIVE_COUNT, len(templates)))

    negatives = []
    for i, tmpl in enumerate(chosen):
        q = tmpl.replace("{product}", product_name)
        negatives.append({
            "key": f"neg_auto_{doc_type}_{i}",
            "intent": "拒答",
            "category": _pick_category(doc_type),
            "answer_type": "unanswerable",
            "chunk_ids": [],
            "hint": "",
            "product_name": product_name,
            "question_override": q,  # 直接指定问题，不调 LLM
        })
    return negatives


# ── 主入口 ──

def auto_generate_buckets(
    jsonl_path: str,
    max_questions: int = 30,
) -> tuple[list[dict], dict, list[dict]]:
    """扫描一个 JSONL，自动生成任务桶 + 源数据。

    Args:
        jsonl_path: paged.jsonl 文件路径
        max_questions: 最多生成的 QA 数

    Returns:
        (tasks, by_id, all_chunks)
        - tasks: [task_dict, ...]  可答题 + 负样本
        - by_id: {chunk_id: chunk}  供 gen_one_qa 使用
        - all_chunks: [chunk, ...]  供 gold.py fill_gold_ids 使用
    """
    # 1. 加载 JSONL
    all_chunks = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                all_chunks.append(json.loads(line))

    if not all_chunks:
        log_event(f"[AUTO] {jsonl_path}: 空文件，跳过")
        return [], {}, []

    by_id = {c["chunk_id"]: c for c in all_chunks}
    sample = all_chunks[0]
    product_name = sample.get("product_name", "未知产品")
    company_name = sample.get("company_name", "未知公司")
    doc_type = sample.get("doc_type", "other")

    log_event(f"[AUTO] {jsonl_path}")
    log_event(f"       公司={company_name}  产品={product_name}  类型={doc_type}")
    log_event(f"       共 {len(all_chunks)} chunks")

    # 2. 筛选 QA 级 chunk
    selected = _select_chunks(all_chunks, max_total=max_questions)
    log_event(f"       筛选出 {len(selected)} 个 QA 级 chunk（上限 {max_questions}）")

    # 3. 构建可答题 task
    tasks = []
    for i, chunk in enumerate(selected):
        task = build_task_from_chunk(chunk, doc_type, product_name, i)
        tasks.append(task)

    # 4. 构建负样本
    negatives = build_auto_negatives(doc_type, product_name)
    log_event(f"       生成 {len(negatives)} 个负样本")

    all_tasks = tasks + negatives
    log_event(f"       共 {len(all_tasks)} 个任务桶（{len(tasks)} 可答 + {len(negatives)} 拒答）")

    return all_tasks, by_id, all_chunks
