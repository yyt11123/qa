# -*- coding: utf-8 -*-
"""
入口编排器：按 §8 / §12 串联 qa_gen 包各模块。

两种模式：
  python generate_qa.py           # 手动模式（使用 buckets.py 的硬编码桶）
  python generate_qa.py --auto    # 自动模式（读取 auto_config.py 的 JSONL_TARGETS）

LLM (qwen-plus) 生成 + Embedding (text-embedding-v4) 语义去重，
从 jsonl 生成 QA，输出到 ./output/。
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from qa_gen.config import (
    INPUT_JSONL,
    OUT_DIR,
    OUT_XLSX,
    OUT_LOG,
    MAX_LLM_CALLS,
    _stats,
    log_event,
)
from qa_gen.data_io import load_chunks, _norm
from qa_gen.buckets import BUCKETS, build_sys_prompt
from qa_gen.generate import gen_one_qa, gen_negatives
from qa_gen.dedup import dedup_by_embedding
from qa_gen.validate import validate_rows
from qa_gen.writer import write_xlsx, write_log


def run_manual_mode():
    """原有手动模式：使用 buckets.py 中硬编码的 BUCKETS。"""
    if not os.getenv("DASHSCOPE_API_KEY"):
        log_event("[FATAL] 环境变量 DASHSCOPE_API_KEY 未设置。")
        sys.exit(1)
    os.makedirs(OUT_DIR, exist_ok=True)

    log_event("[STEP1] 加载 jsonl 与建索引")
    chunks, by_id = load_chunks(INPUT_JSONL)
    log_event(f"  共 {len(chunks)} 个 chunk")

    _stats["log_assumptions"].extend([
        "总量 N=40（§11 默认值）",
        "负样本 6 条（§11 默认值）",
        "去重相似度阈值 0.85（同 section 桶内）",
        "G 列 embedding 语义补全默认关闭",
        "负样本不进行 embedding 去重",
        "G 列剔除 doc_summary 类（§5 规则4），除非该 chunk 是 primary_chunk_id 来源",
    ])

    log_event("[STEP2] LLM 生成可答题")
    answerable_rows = []
    for task in BUCKETS:
        if _stats["llm_calls"] >= MAX_LLM_CALLS:
            log_event("[STOP] LLM 调用上限触发，停止生成。")
            break
        log_event(f"  · 生成 {task['key']} {task['intent']}/{task['answer_type']} hint={task['hint'][:40]}")
        row = gen_one_qa(task, by_id, chunks)
        if row:
            answerable_rows.append(row)
    log_event(f"  共生成 {len(answerable_rows)} 条可答题（应得 {len(BUCKETS)}）")

    log_event("[STEP3] 构造负样本")
    negatives = gen_negatives()
    log_event(f"  共 {len(negatives)} 条负样本")

    rows = answerable_rows + negatives

    log_event("[STEP4] embedding 语义去重")
    n_before = len(rows)
    rows = dedup_by_embedding(rows)
    n_dedup = n_before - len(rows)
    drop_stats = {"dedup_dropped": n_dedup}

    log_event("[STEP5] 校验 §9")
    issues, short_ratio = validate_rows(rows, by_id, chunks)
    if issues:
        log_event(f"[VALIDATE] {len(issues)} 项问题：")
        for idx, msg in issues[:30]:
            log_event(f"  - row#{idx}: {msg}")
    log_event(f"[VALIDATE] question < 30 字比例：{short_ratio:.0%}")

    # 自动修复：丢弃严重不合规条目
    rows = _auto_fix(rows, by_id)

    log_event(f"[STEP6] 写出 xlsx → {OUT_XLSX}")
    write_xlsx(rows, OUT_XLSX)

    log_event(f"[STEP7] 写出运行日志 → {OUT_LOG}")
    write_log(rows, OUT_LOG, drop_stats)

    print("\n=== DONE ===")
    print(f"rows = {len(rows)} → {OUT_XLSX}")
    print(f"log → {OUT_LOG}")


def run_auto_mode():
    """自动模式：读取 auto_config.JSONL_TARGETS，逐文档生成 QA。"""
    if not os.getenv("DASHSCOPE_API_KEY"):
        log_event("[FATAL] 环境变量 DASHSCOPE_API_KEY 未设置。")
        sys.exit(1)
    os.makedirs(OUT_DIR, exist_ok=True)

    from qa_gen.auto_config import JSONL_TARGETS
    from qa_gen.auto_buckets import auto_generate_buckets

    all_rows = []

    for jsonl_path, max_q in JSONL_TARGETS:
        if _stats["llm_calls"] >= MAX_LLM_CALLS:
            log_event("[STOP] LLM 调用上限触发，停止生成。")
            break

        full_path = jsonl_path
        if not os.path.isabs(full_path):
            full_path = os.path.join(os.path.dirname(__file__) or ".", jsonl_path)

        if not os.path.exists(full_path):
            log_event(f"[SKIP] 文件不存在: {full_path}")
            continue

        log_event(f"\n{'='*60}")
        log_event(f"[AUTO] 处理: {jsonl_path}")

        # 1. 自动生成任务桶
        tasks, by_id, all_chunks = auto_generate_buckets(full_path, max_questions=max_q)
        if not tasks:
            continue

        # 2. 获取产品名用于 system prompt
        product_name = tasks[0].get("product_name", "") if tasks else ""
        sys_prompt = build_sys_prompt(product_name)

        # 3. 对每个可答题 task 调用 gen_one_qa
        doc_rows = []
        answerable_tasks = [t for t in tasks if t.get("answer_type") != "unanswerable"]
        negative_tasks = [t for t in tasks if t.get("answer_type") == "unanswerable"]

        log_event(f"  生成 {len(answerable_tasks)} 条可答题 ...")
        for task in answerable_tasks:
            if _stats["llm_calls"] >= MAX_LLM_CALLS:
                log_event("[STOP] LLM 调用上限触发。")
                break
            row = gen_one_qa(task, by_id, all_chunks, sys_prompt=sys_prompt)
            if row:
                doc_rows.append(row)

        # 4. 负样本（不调 LLM）
        log_event(f"  生成 {len(negative_tasks)} 条负样本 ...")
        for task in negative_tasks:
            row = gen_one_qa(task, by_id, all_chunks)  # question_override 走快捷路径
            if row:
                doc_rows.append(row)

        log_event(f"  本文档共生成 {len(doc_rows)} 条 QA")

        # 5. 去重
        n_before = len(doc_rows)
        doc_rows = dedup_by_embedding(doc_rows)
        log_event(f"  去重: {n_before} → {len(doc_rows)} (-{n_before - len(doc_rows)})")

        # 6. 校验 + 自动修复
        issues, short_ratio = validate_rows(doc_rows, by_id, all_chunks)
        if issues:
            log_event(f"  校验问题 {len(issues)} 项")
            for idx, msg in issues[:10]:
                log_event(f"    - row#{idx}: {msg}")
        doc_rows = _auto_fix(doc_rows, by_id)

        # 7. 写单文档 xlsx
        out_xlsx = _make_output_path(jsonl_path)
        write_xlsx(doc_rows, out_xlsx)
        log_event(f"  输出: {out_xlsx}")

        all_rows.extend(doc_rows)

    # 汇总统计
    print(f"\n=== AUTO DONE ===")
    print(f"total rows = {len(all_rows)} across {len(JSONL_TARGETS)} documents")
    print(f"LLM calls: {_stats['llm_calls']}/{MAX_LLM_CALLS}")
    print(f"output dir: {OUT_DIR}")


def _make_output_path(jsonl_path: str) -> str:
    """从 jsonl 路径推导出 xlsx 输出路径。"""
    # output/安盛/愛唯守危疾保障_产品彩页_paged.jsonl
    # → output/安盛/愛唯守危疾保障_产品彩页_QA测评集.xlsx
    base = jsonl_path.replace("_paged.jsonl", "")
    base = base.replace(".jsonl", "")
    return base + "_QA测评集.xlsx"


def _auto_fix(rows, by_id):
    """自动修复：丢弃严重不合规条目。"""
    from qa_gen.data_io import _norm
    fixed = []
    for r in rows:
        bad = False
        if r["answer_type"] != "unanswerable":
            gids = [g for g in r["gold_chunk_ids"].split(";") if g]
            f_ok = any(
                _norm(r["supporting_text"]) in _norm(by_id[g].get("content") or "")
                for g in gids if g in by_id
            )
            if not f_ok:
                bad = True
                log_event(f"[FIX] 丢弃 F 子串校验失败的条目：{r['question'][:30]}…")
            elif len(r["question"]) > 50:
                bad = True
                log_event(f"[FIX] 丢弃 question 过长条目：{r['question'][:30]}…")
        if not bad:
            fixed.append(r)
    log_event(f"  自动修复: {len(rows)} → {len(fixed)} (-{len(rows) - len(fixed)})")
    return fixed


def main():
    if "--auto" in sys.argv:
        run_auto_mode()
    else:
        run_manual_mode()


if __name__ == "__main__":
    main()
