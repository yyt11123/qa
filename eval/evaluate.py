#!/usr/bin/env python3
"""
评测脚本骨架 —— 用于评估保险 RAG 系统的检索质量与生成质量。

使用方式：
    python evaluate.py \\
        --dataset eval/qa_dataset.jsonl \\
        --output eval/results.json

在接入真实检索系统前，使用桩函数（stub）占位：
  - retrieve_stub(): 模拟 DashVector 检索，返回 Top-K chunks
  - generate_answer_stub(): 模拟 LLM 基于 retrieved chunks 生成回答

接入真实系统时，只需替换这两个函数即可，其余评测逻辑无需修改。

评测指标：
  【检索】
    - Recall@K  (K=1,3,5,10)
    - MRR       (Mean Reciprocal Rank)
    - Hit Rate  (首位命中率 / Precision@K)
    命中判定：gold 的 page 与 retrieved chunk 的 page 匹配，
              且 gold 的 text_snippet 与 retrieved chunk 的 text 字符重叠 ≥ 阈值

  【生成】
    - LLM-as-judge 接口占位（TODO），判断 final_answer 对 reference_answer 的正确性/忠实度

  【拒答】
    - unanswerable 题目的拒答正确率（RAG 是否正确表示"资料中查不到"）
"""

import json
import os
import re
import sys
import argparse
from collections import defaultdict
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# 配置常量（不硬编码任何文件路径或密钥）
# ═══════════════════════════════════════════════════════════════════════════════

# 检索命中判定的字符重叠阈值
OVERLAP_THRESHOLD = 0.6

# 拒答关键词（用于判断 RAG 输出是否表示"资料中查不到"）
REFUSAL_PATTERNS = [
    "无法回答",
    "無法回答",
    "无法提供",
    "無法提供",
    "资料中查不到",
    "資料中查不到",
    "未提供该信息",
    "未提供該信息",
    "無法從本文檔回答",
    "无法从本文档回答",
    "没有相关信息",
    "沒有相關信息",
    "未提及",
    "不包含",
    "无法找到",
    "無法找到",
    "暂无相关",
    "暫無相關",
    "无相关信息",
    "無相關信息",
    "未能找到",
    "資料不足",
    "资料不足",
    "无法确定",
    "不确定",
    "不確定",
    "sorry",
    "I cannot",
    "not available",
    "no information",
]

# 评测时使用的 K 值列表
K_VALUES = [1, 3, 5, 10]


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def load_dataset(path: str) -> list[dict]:
    """加载 QA 评测数据集。"""
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    print(f"[加载] 从 {path} 加载了 {len(records)} 条评测数据")
    return records


def normalize(text: str) -> str:
    """归一化文本：合并空白字符。"""
    if not text:
        return ""
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_char_overlap(text_a: str, text_b: str, n: int = 3) -> float:
    """
    计算两段文本的 n-gram 字符重叠度。
    使用 3-gram 避免中文常见字的虚高重叠（比单字集更可靠）。

    返回: 0.0 ~ 1.0 的重叠比例（以较短文本的 n-gram 数量为分母）
    """
    if not text_a or not text_b:
        return 0.0

    norm_a = normalize(text_a)
    norm_b = normalize(text_b)

    # 直接包含检查（最可靠）
    if norm_a in norm_b or norm_b in norm_a:
        return 1.0

    def ngrams(s: str, n: int):
        return {s[i : i + n] for i in range(len(s) - n + 1)}

    a_ngrams = ngrams(norm_a, n)
    b_ngrams = ngrams(norm_b, n)

    if not a_ngrams or not b_ngrams:
        return 0.0

    # 以 gold snippet 的 n-gram 数量为分母
    intersection = len(a_ngrams & b_ngrams)
    return intersection / len(a_ngrams)


def is_hit(gold_evidence: dict, retrieved_chunk: dict, threshold: float = OVERLAP_THRESHOLD) -> bool:
    """
    判断一条 gold_evidence 是否被某个 retrieved_chunk 命中。

    条件：
      1. 页码匹配：gold 的 page 与 retrieved chunk 的 page 相同
      2. 文本重叠：gold 的 text_snippet 与 retrieved chunk 的 text 重叠度 ≥ threshold
    """
    # 页码匹配
    gold_page = gold_evidence.get("page")
    ret_page = retrieved_chunk.get("page")
    if gold_page is not None and ret_page is not None:
        if gold_page != ret_page:
            return False

    # 文本重叠
    gold_text = gold_evidence.get("text_snippet", "")
    ret_text = retrieved_chunk.get("text", "")
    overlap = compute_char_overlap(gold_text, ret_text)
    return overlap >= threshold


def check_refusal(final_answer: str) -> bool:
    """判断 RAG 输出是否表示拒答（资料中查不到）。"""
    if not final_answer:
        return True  # 空回答视为拒答
    lower = final_answer.lower()
    for pattern in REFUSAL_PATTERNS:
        if pattern.lower() in lower:
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# 桩函数（stub）—— 接入真实系统时，只需替换这里
# ═══════════════════════════════════════════════════════════════════════════════

def retrieve_stub(question: str, top_k: int = 10) -> list[dict]:
    """
    【桩函数】模拟 DashVector 检索。

    真实接入时替换为：
      - 调用 DashVector 的 embedding 检索
      - 返回 Top-K 个 chunk，每个包含 page 和 text 字段

    返回格式: [{page: int, text: str, score: float}, ...]
    """
    # 这里返回空列表，评测脚本会正确处理（所有检索指标为 0）
    return []


def generate_answer_stub(question: str, retrieved_chunks: list[dict]) -> str:
    """
    【桩函数】模拟 LLM 基于检索结果生成回答。

    真实接入时替换为：
      - 拼接 retrieved_chunks 为 context
      - 调用 LLM（如 GPT-4 / Claude）生成最终回答

    返回: str
    """
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# RAG 系统包装器 —— 把检索 + 生成串起来
# ═══════════════════════════════════════════════════════════════════════════════

def run_rag_system(question: str, top_k: int = 10) -> dict:
    """
    执行一次完整的 RAG 流程：检索 + 生成。

    返回格式（统一）：
      {
        "question": str,
        "retrieved_chunks": [{page, text, score}, ...],
        "final_answer": str,
      }
    """
    retrieved_chunks = retrieve_stub(question, top_k=top_k)
    final_answer = generate_answer_stub(question, retrieved_chunks)
    return {
        "question": question,
        "retrieved_chunks": retrieved_chunks,
        "final_answer": final_answer,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 评测逻辑
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_retrieval(
    qa_records: list[dict],
    top_k: int = 10,
    threshold: float = OVERLAP_THRESHOLD,
) -> dict:
    """
    评测检索质量。

    对每条可回答的题（answer_type != unanswerable）：
      - 对其每个 gold_evidence，检查在 Top-K 个 retrieved chunk 中是否有命中
      - 记录第一个命中的 rank（用于 MRR）
      - 计算 Recall@K、MRR、Hit Rate

    返回: 检索指标汇总 + 逐条明细
    """
    details = []

    # 汇总统计
    total_answerable = 0
    total_gold_evidences = 0
    total_hits_at_k = {k: 0 for k in K_VALUES}
    total_hit_evidences_at_k = {k: 0 for k in K_VALUES}  # 按 evidence 粒度的命中数
    rr_sum = 0.0  # reciprocal rank 累加
    question_level_hits = {k: 0 for k in K_VALUES}

    for record in qa_records:
        if record["answer_type"] == "unanswerable":
            continue  # unanswerable 不参与检索评测

        total_answerable += 1
        gold_evidences = record.get("gold_evidence", [])
        if not gold_evidences:
            continue

        total_gold_evidences += len(gold_evidences)

        # 运行 RAG 系统（桩模式）
        rag_result = run_rag_system(record["question"], top_k=top_k)
        retrieved = rag_result["retrieved_chunks"]

        # 对每个 gold_evidence 检查命中情况
        evidence_hits = []
        first_hit_rank = None

        for ev in gold_evidences:
            ev_hit_rank = None
            for rank, chunk in enumerate(retrieved, start=1):
                if is_hit(ev, chunk, threshold=threshold):
                    ev_hit_rank = rank
                    break
            evidence_hits.append({
                "page": ev["page"],
                "text_snippet": ev["text_snippet"][:100],
                "hit_rank": ev_hit_rank,
                "is_hit": ev_hit_rank is not None,
            })
            if ev_hit_rank is not None:
                if first_hit_rank is None or ev_hit_rank < first_hit_rank:
                    first_hit_rank = ev_hit_rank

        # 计算该题在各个 K 下的命中情况
        q_hit_at_k = {}
        for k in K_VALUES:
            q_hit = any(h["hit_rank"] is not None and h["hit_rank"] <= k for h in evidence_hits)
            q_hit_at_k[k] = q_hit
            if q_hit:
                question_level_hits[k] += 1
                total_hit_evidences_at_k[k] += sum(
                    1 for h in evidence_hits if h["hit_rank"] is not None and h["hit_rank"] <= k
                )

        # MRR（以第一个命中的 rank 为准；如果没有任何命中则为 0）
        if first_hit_rank is not None:
            rr_sum += 1.0 / first_hit_rank

        details.append({
            "id": record["id"],
            "question": record["question"],
            "answer_type": record["answer_type"],
            "num_gold_evidences": len(gold_evidences),
            "num_retrieved": len(retrieved),
            "first_hit_rank": first_hit_rank,
            "evidence_hits": evidence_hits,
        })

    # 计算聚合指标
    retrieval_metrics = {
        "total_answerable": total_answerable,
        "total_gold_evidences": total_gold_evidences,
        "Recall@K": {},
        "Precision@K": {},
        "HitRate@K": {},
        "MRR": rr_sum / total_answerable if total_answerable > 0 else 0.0,
    }

    for k in K_VALUES:
        # Recall@K: 命中的 question 数 / 总可回答 question 数
        retrieval_metrics["Recall@K"][f"Recall@{k}"] = (
            question_level_hits[k] / total_answerable if total_answerable > 0 else 0.0
        )
        # Precision@K / Hit Rate
        retrieval_metrics["HitRate@K"][f"HitRate@{k}"] = (
            question_level_hits[k] / total_answerable if total_answerable > 0 else 0.0
        )

    return retrieval_metrics, details


def evaluate_generation(
    qa_records: list[dict],
    rag_results: dict[int, dict],
) -> dict:
    """
    【占位】LLM-as-judge 评测生成质量。

    TODO:
      1. 对每条可回答的题，取 reference_answer 和 RAG 的 final_answer
      2. 调用 LLM-as-judge（如 GPT-4）判断：
         - correctness: 回答是否正确（1-5 分）
         - faithfulness: 回答是否忠实于检索到的原文（1-5 分）
         - completeness: 是否遗漏关键信息（1-5 分）
      3. 对 unanswerable 的题，判断 final_answer 是否表达了"无法回答"

    参考 prompt 模板（接入时替换为真实 LLM 调用）：

      system_prompt = \"\"\"你是一个保险领域的评测专家。请根据以下标准对 RAG 系统的回答进行评分：
      - correctness: 回答的事实是否与标准答案一致（1-5）
      - faithfulness: 回答是否严格基于提供的参考原文，没有编造（1-5）
      - completeness: 回答是否覆盖了标准答案的所有关键点（1-5）
      请以 JSON 格式输出：{"correctness": int, "faithfulness": int, "completeness": int, "reason": str}\"\"\"

      user_prompt = f\"\"\"标准答案：{reference_answer}
      参考原文：{gold_evidence}
      RAG回答：{final_answer}
      请评分：\"\"\"

    这里先用桩返回值占位。
    """
    gen_metrics = {
        "method": "LLM-as-judge (TODO: 接入真实模型)",
        "avg_correctness": None,
        "avg_faithfulness": None,
        "avg_completeness": None,
        "details": [],
    }

    for record in qa_records:
        qid = record["id"]
        rag = rag_results.get(qid, {})
        gen_metrics["details"].append({
            "id": qid,
            "question": record["question"],
            "reference_answer": record["reference_answer"],
            "final_answer": rag.get("final_answer", ""),
            "judge_scores": None,  # TODO: 填入 LLM-as-judge 的评分
        })

    return gen_metrics


def evaluate_unanswerable(qa_records: list[dict], rag_results: dict[int, dict]) -> dict:
    """
    评测 unanswerable 题目的拒答正确率。

    - 正确拒答:  RAG 的 final_answer 表示"资料中查不到"  → True Positive
    - 错误回答:  RAG 尝试给出实质回答但题目本不可答        → False Positive
    - 错误拒答:  题目可答但 RAG 拒答了                      → False Negative（在可答题中另统计）
    """
    total_unanswerable = 0
    correct_refusals = 0
    details = []

    for record in qa_records:
        if record["answer_type"] != "unanswerable":
            continue
        total_unanswerable += 1
        qid = record["id"]
        rag = rag_results.get(qid, {})
        final_answer = rag.get("final_answer", "")
        is_refusal = check_refusal(final_answer)

        if is_refusal:
            correct_refusals += 1

        details.append({
            "id": qid,
            "question": record["question"],
            "final_answer": final_answer,
            "is_refusal": is_refusal,
            "correct": is_refusal,
        })

    return {
        "total_unanswerable": total_unanswerable,
        "correct_refusals": correct_refusals,
        "refusal_accuracy": (
            correct_refusals / total_unanswerable if total_unanswerable > 0 else 0.0
        ),
        "details": details,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="保险 RAG 系统评测")
    parser.add_argument("--dataset", default="eval/qa_dataset.jsonl", help="QA 评测数据集路径")
    parser.add_argument("--output", default="eval/results.json", help="评测结果输出路径")
    parser.add_argument("--top-k", type=int, default=10, help="检索返回的 Top-K 数量")
    parser.add_argument("--threshold", type=float, default=OVERLAP_THRESHOLD,
                        help=f"检索命中判定的字符重叠阈值（默认 {OVERLAP_THRESHOLD}）")
    args = parser.parse_args()

    threshold = args.threshold

    # 1. 加载数据集
    qa_records = load_dataset(args.dataset)

    # 2. 运行 RAG 系统（对所有题），收集结果
    print(f"\n[评测] 运行 RAG 系统（Top-{args.top_k}）...")
    rag_results = {}
    for record in qa_records:
        rag_results[record["id"]] = run_rag_system(record["question"], top_k=args.top_k)

    # 3. 检索评测
    print("[评测] 计算检索指标...")
    retrieval_metrics, retrieval_details = evaluate_retrieval(
        qa_records, top_k=args.top_k, threshold=threshold
    )

    # 4. 生成评测
    print("[评测] 计算生成指标（LLM-as-judge 占位）...")
    gen_metrics = evaluate_generation(qa_records, rag_results)

    # 5. 拒答评测
    print("[评测] 计算拒答指标...")
    refusal_metrics = evaluate_unanswerable(qa_records, rag_results)

    # 6. 汇总结果
    results = {
        "config": {
            "dataset": args.dataset,
            "top_k": args.top_k,
            "overlap_threshold": threshold,
        },
        "summary": {
            "total_questions": len(qa_records),
            "answerable": retrieval_metrics["total_answerable"],
            "unanswerable": refusal_metrics["total_unanswerable"],
            "retrieval": {
                "MRR": round(retrieval_metrics["MRR"], 4),
                **{k: round(v, 4) for k, v in retrieval_metrics["Recall@K"].items()},
            },
            "generation": {
                "method": gen_metrics["method"],
                "avg_correctness": gen_metrics["avg_correctness"],
                "avg_faithfulness": gen_metrics["avg_faithfulness"],
                "avg_completeness": gen_metrics["avg_completeness"],
            },
            "refusal_accuracy": round(refusal_metrics["refusal_accuracy"], 4),
        },
        "retrieval_details": retrieval_details,
        "generation_details": gen_metrics["details"],
        "refusal_details": refusal_metrics["details"],
    }

    # 7. 输出
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 评测结果已写入 {args.output}")

    # 8. 打印摘要
    print("\n" + "=" * 60)
    print("评测结果摘要")
    print("=" * 60)
    s = results["summary"]
    print(f"  总题目数:    {s['total_questions']}")
    print(f"  可答题:      {s['answerable']}")
    print(f"  不可答题:    {s['unanswerable']}")
    print(f"\n  【检索指标】")
    print(f"  MRR:         {s['retrieval']['MRR']:.4f}")
    for k in K_VALUES:
        key = f"Recall@{k}"
        if key in s["retrieval"]:
            print(f"  Recall@{k}:    {s['retrieval'][key]:.4f}")
    print(f"\n  【生成指标】")
    print(f"  方法:         {s['generation']['method']}")
    print(f"\n  【拒答指标】")
    print(f"  拒答正确率:   {s['refusal_accuracy']:.4f} ({refusal_metrics['correct_refusals']}/{refusal_metrics['total_unanswerable']})")
    print("=" * 60)


if __name__ == "__main__":
    main()
