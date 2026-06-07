#!/usr/bin/env python3
"""
将 愛唯守_QA测评集.xlsx 转换为标准 JSONL 评测数据集。

输出格式（每条记录）：
  - id: 自增编号
  - question: 问题文本
  - reference_answer: 标准答案
  - company: 公司名称（从源 jsonl 的 company_name 统一取）
  - product_name: 产品名称
  - answer_type: single_fact / multi_chunk / table_lookup / unanswerable
  - intent: 意图分类
  - gold_evidence: [{page: int, text_snippet: str}, ...]  —— 评测的核心依据
  - gold_chunk_ids: [str, ...]  —— 仅供自查，不参与评测

校验逻辑：
  对每条可回答的题（answer_type != unanswerable）：
    1. gold_chunk_ids 是否真的存在于 jsonl 中
    2. page 是否在 chunk 的 page_start ~ page_end 范围内
    3. text 是否能在 chunk 的 content 中找到（允许格式差异，用模糊匹配）
  校验不通过的行打印出来供人工核对。
"""

import json
import os
import re
import sys
from pathlib import Path

import openpyxl


# ── 配置（不硬编码任何敏感信息）─────────────────────────────────────────────

XLSX_PATH = "愛唯守_QA测评集.xlsx"
JSONL_SOURCE_PATH = "愛唯守危疾保障_产品彩页_paged(1).jsonl"
OUTPUT_DIR = "eval"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "qa_dataset.jsonl")

# xlsx 列映射（0-based，从数据行开始算；数据行从第3行开始，前两行是表头）
COL = {
    "category": 0,      # A列 - 分类
    "question": 1,      # B列 - question
    "reference_answer": 2,  # C列 - answers
    "document": 3,      # D列 - document（文件名）
    "page": 4,          # E列 - page（页码）
    "text": 5,          # F列 - text（支撑原文）
    "gold_chunk_ids": 6,  # G列 - gold_chunk_ids
    "answer_type": 7,   # H列 - answer_type
    "intent": 8,        # I列 - intent
}


# ── 辅助函数 ─────────────────────────────────────────────────────────────────

def load_jsonl(path: str) -> dict:
    """
    加载源文档 JSONL，按 chunk_id 建立索引。
    返回: {chunk_id: {page_start, page_end, content, ...}, ...}
    """
    chunks = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            chunks[obj["chunk_id"]] = obj
    print(f"[加载] 从 {path} 加载了 {len(chunks)} 个 chunk")
    return chunks


def fuzzy_find(text_snippet: str, content: str, threshold: float = 0.5) -> bool:
    """
    检查 text_snippet 是否「大致」出现在 content 中。
    策略：
      1. 归一化后直接子串匹配。
      2. 基于 3-gram（三元字符组）的重叠度 —— 避免单字符集重叠造成的误判
         （中文单字集重叠度极易虚高）。
    """
    if not text_snippet or not content:
        return False

    # 归一化：去掉多余空白
    def normalize(s: str) -> str:
        s = s.replace("\n", " ").replace("\r", " ").replace("\t", " ")
        s = re.sub(r"\s+", " ", s).strip()
        return s

    norm_text = normalize(text_snippet)
    norm_content = normalize(content)

    # 步骤1：直接子串匹配
    if norm_text in norm_content:
        return True
    if norm_content in norm_text:
        return True

    # 步骤2：3-gram 重叠度（对中文更可靠）
    def ngrams(s: str, n: int = 3):
        return {s[i:i + n] for i in range(len(s) - n + 1)}

    text_ngrams = ngrams(norm_text)
    if not text_ngrams:
        return False
    content_ngrams = ngrams(norm_content)
    overlap = len(text_ngrams & content_ngrams) / len(text_ngrams)
    return overlap >= threshold


def parse_chunk_ids(raw: str | None) -> list[str]:
    """解析 xlsx 中用分号分隔的 chunk_id 字段。"""
    if raw is None:
        return []
    raw = str(raw).strip()
    if not raw:
        return []
    # 支持中文分号和英文分号
    ids = re.split(r"[;；]", raw)
    return [cid.strip() for cid in ids if cid.strip()]


def parse_page(raw) -> int | None:
    """解析页码，处理 None 和空值。"""
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


# ── 主逻辑 ───────────────────────────────────────────────────────────────────

def main():
    # 1. 加载源 jsonl
    print("=" * 60)
    print("步骤1：加载源文档 JSONL ...")
    chunk_map = load_jsonl(JSONL_SOURCE_PATH)

    # 取出公司名和产品名（所有 chunk 应该一致）
    sample = next(iter(chunk_map.values()))
    company_name = sample["company_name"]
    product_name = sample["product_name"]
    print(f"  公司: {company_name}")
    print(f"  产品: {product_name}")

    # 2. 加载 xlsx
    print("\n步骤2：加载 xlsx ...")
    wb = openpyxl.load_workbook(XLSX_PATH)
    ws = wb.active
    print(f"  Sheet: {ws.title}, 行数: {ws.max_row}, 列数: {ws.max_column}")

    # 3. 解析数据行（从第3行开始）
    print("\n步骤3：解析并校验 QA 数据 ...")
    qa_list = []
    validation_errors = []  # (excel_row, message)

    for row_idx in range(3, ws.max_row + 1):  # openpyxl 行号从1开始
        # 读取各列
        question = ws.cell(row=row_idx, column=COL["question"] + 1).value
        if question is None or str(question).strip() == "":
            continue  # 跳过空行

        reference_answer = str(ws.cell(row=row_idx, column=COL["reference_answer"] + 1).value or "")
        raw_page = ws.cell(row=row_idx, column=COL["page"] + 1).value
        text_snippet = str(ws.cell(row=row_idx, column=COL["text"] + 1).value or "") if ws.cell(row=row_idx, column=COL["text"] + 1).value else ""
        raw_chunk_ids = str(ws.cell(row=row_idx, column=COL["gold_chunk_ids"] + 1).value or "") if ws.cell(row=row_idx, column=COL["gold_chunk_ids"] + 1).value else ""
        answer_type = str(ws.cell(row=row_idx, column=COL["answer_type"] + 1).value or "").strip()
        intent = str(ws.cell(row=row_idx, column=COL["intent"] + 1).value or "").strip()

        question = str(question).strip()
        page = parse_page(raw_page)
        gold_chunk_ids = parse_chunk_ids(raw_chunk_ids)
        excel_row_display = row_idx  # Excel 显示行号

        # ── 处理 unanswerable ──
        if answer_type == "unanswerable":
            qa_list.append({
                "id": len(qa_list) + 1,
                "question": question,
                "reference_answer": reference_answer,
                "company": company_name,
                "product_name": product_name,
                "answer_type": "unanswerable",
                "intent": intent,
                "gold_evidence": [],
                "gold_chunk_ids": gold_chunk_ids,
            })
            continue

        # ── 可回答的题：校验 ──
        if not gold_chunk_ids:
            validation_errors.append((excel_row_display, "gold_chunk_ids 为空（可回答题型）"))
            continue

        if page is None:
            validation_errors.append((excel_row_display, "page 为空（可回答题型）"))

        # 判断是否为多 chunk 场景
        is_multi_chunk = len(gold_chunk_ids) > 1

        # ── 先做整体校验（xlsx 的 text 是否至少匹配其中一个 chunk）──
        if text_snippet and not is_multi_chunk:
            # 单 chunk：必须匹配
            cid = gold_chunk_ids[0]
            if cid in chunk_map:
                if not fuzzy_find(text_snippet, chunk_map[cid].get("content", "")):
                    validation_errors.append(
                        (excel_row_display,
                         f"chunk_id [{cid}] 的 content 中未找到 text_snippet（片段: {text_snippet[:60]}...）")
                    )
        elif text_snippet and is_multi_chunk:
            # 多 chunk：xlsx 的 text 至少匹配其中一个即可
            any_matched = any(
                fuzzy_find(text_snippet, chunk_map[cid].get("content", ""))
                for cid in gold_chunk_ids if cid in chunk_map
            )
            if not any_matched:
                validation_errors.append(
                    (excel_row_display,
                     f"所有 gold_chunk_ids 的 content 中均未找到 text_snippet（片段: {text_snippet[:60]}...）")
                )

        # ── 逐 chunk 构建 gold_evidence ──
        gold_evidence = []
        for cid in gold_chunk_ids:
            if cid not in chunk_map:
                validation_errors.append(
                    (excel_row_display, f"chunk_id [{cid}] 在 jsonl 中不存在")
                )
                continue

            chunk = chunk_map[cid]
            c_page_start = chunk.get("page_start")
            c_page_end = chunk.get("page_end")
            c_content = chunk.get("content", "")

            # 校验页码：xlsx 的 page 必须在所有 chunk 的 page_range 合集之内
            if page is not None and c_page_start is not None and c_page_end is not None:
                if not (c_page_start <= page <= c_page_end):
                    validation_errors.append(
                        (excel_row_display,
                         f"chunk_id [{cid}] 的 page_range=[{c_page_start},{c_page_end}] 与 xlsx page={page} 不匹配")
                    )

            if is_multi_chunk:
                # ── 多 chunk：每个 evidence 取它自己 chunk 的 content 和 page ──
                evidence_page = c_page_start if c_page_start is not None else page
                evidence_text = c_content
            else:
                # ── 单 chunk：用 xlsx 手工标注的 text 和 page（更精准）──
                evidence_page = page if page is not None else (c_page_start or 0)
                evidence_text = text_snippet if text_snippet else c_content

            gold_evidence.append({
                "page": evidence_page,
                "text_snippet": evidence_text,
            })

        qa_list.append({
            "id": len(qa_list) + 1,
            "question": question,
            "reference_answer": reference_answer,
            "company": company_name,
            "product_name": product_name,
            "answer_type": answer_type,
            "intent": intent,
            "gold_evidence": gold_evidence,
            "gold_chunk_ids": gold_chunk_ids,
        })

    # 4. 输出校验结果
    print("\n" + "=" * 60)
    print("步骤4：校验结果")
    if validation_errors:
        print(f"  ⚠ 发现 {len(validation_errors)} 个校验问题，请人工核对：")
        for row_num, msg in validation_errors:
            print(f"    [Excel第{row_num}行] {msg}")
    else:
        print("  ✅ 所有可回答题目的校验均通过！")
    print(f"  共解析 {len(qa_list)} 条 QA")

    # 5. 输出 JSONL
    print("\n步骤5：写出 JSONL ...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for item in qa_list:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"  ✅ 已写入 {OUTPUT_PATH}（{len(qa_list)} 条）")

    # 6. 统计信息
    print("\n" + "=" * 60)
    print("步骤6：数据集统计")
    type_counts = {}
    intent_counts = {}
    for item in qa_list:
        type_counts[item["answer_type"]] = type_counts.get(item["answer_type"], 0) + 1
        intent_counts[item["intent"]] = intent_counts.get(item["intent"], 0) + 1
    print(f"  answer_type 分布: {type_counts}")
    print(f"  intent 分布: {intent_counts}")
    print(f"  unanswerable 题数: {type_counts.get('unanswerable', 0)}")
    answerable = sum(1 for item in qa_list if item["gold_evidence"])
    print(f"  有 gold_evidence 的题数: {answerable}")

    if validation_errors:
        print(f"\n  ⚠ 有校验问题的行已跳过/仍输出但标记了错误，请核查后重新运行。")


if __name__ == "__main__":
    main()
