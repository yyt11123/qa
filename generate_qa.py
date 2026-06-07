# -*- coding: utf-8 -*-
"""
入口编排器：按 §8 / §12 串联 qa_gen 包各模块。
LLM (qwen-plus) 生成 + Embedding (text-embedding-v4) 语义去重，
从单一 jsonl 生成约 40 条 QA，输出到 ./output/。
所有业务逻辑在 qa_gen/ 包内，本文件只负责编排。
"""

import os, sys

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
from qa_gen.buckets import BUCKETS
from qa_gen.generate import gen_one_qa, gen_negatives
from qa_gen.dedup import dedup_by_embedding
from qa_gen.validate import validate_rows
from qa_gen.writer import write_xlsx, write_log


def main():
    if not os.getenv("DASHSCOPE_API_KEY"):
        log_event("[FATAL] 环境变量 DASHSCOPE_API_KEY 未设置。")
        sys.exit(1)
    os.makedirs(OUT_DIR, exist_ok=True)

    log_event("[STEP1] 加载 jsonl 与建索引")
    chunks, by_id = load_chunks(INPUT_JSONL)
    log_event(f"  共 {len(chunks)} 个 chunk")

    # 默认假设记录（§12 要求）
    _stats["log_assumptions"].extend(
        [
            "总量 N=40（§11 默认值）",
            "负样本 6 条（§11 默认值）",
            "去重相似度阈值 0.85（同 section 桶内）",
            "G 列 embedding 语义补全默认关闭（§8.1 第3步可选项；关键词/子串匹配已足够）",
            "负样本不进行 embedding 去重",
            "G 列剔除 doc_summary 类（§5 规则4），除非该 chunk 是 primary_chunk_id 来源",
        ]
    )

    log_event("[STEP2] LLM 生成可答题")
    answerable_rows = []
    for task in BUCKETS:
        if _stats["llm_calls"] >= MAX_LLM_CALLS:
            log_event("[STOP] LLM 调用上限触发，停止生成。")
            break
        log_event(
            f"  · 生成 {task['key']} {task['intent']}/{task['answer_type']} hint={task['hint'][:40]}"
        )
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
    fixed_rows = []
    for r in rows:
        bad = False
        if r["answer_type"] != "unanswerable":
            gids = [g for g in r["gold_chunk_ids"].split(";") if g]
            f_ok = any(
                _norm(r["supporting_text"]) in _norm(by_id[g].get("content") or "")
                for g in gids
                if g in by_id
            )
            if not f_ok:
                bad = True
                log_event(f"[FIX] 丢弃 F 子串校验失败的条目：{r['question'][:30]}…")
            elif len(r["question"]) > 50:
                bad = True
                log_event(f"[FIX] 丢弃 question 过长条目：{r['question'][:30]}…")
        if not bad:
            fixed_rows.append(r)
    rows = fixed_rows
    log_event(f"  最终 {len(rows)} 条")

    log_event(f"[STEP6] 写出 xlsx → {OUT_XLSX}")
    write_xlsx(rows, OUT_XLSX)

    log_event(f"[STEP7] 写出运行日志 → {OUT_LOG}")
    write_log(rows, OUT_LOG, drop_stats)

    # 简短控制台总结
    print("\n=== DONE ===")
    print(f"rows = {len(rows)} → {OUT_XLSX}")
    print(f"log → {OUT_LOG}")


if __name__ == "__main__":
    main()
