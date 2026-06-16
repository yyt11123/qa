# qa_generate_v4 — 保险 RAG 评测数据集批量生成框架

基于 LLM + Embedding 自动从保险条款文档（JSONL）批量生成 QA 评测集，输出 xlsx + JSONL。

## 技术栈

| 组件 | 配置 |
|---|---|
| LLM 模型 | `qwen-plus`（阿里云 DashScope / 百炼） |
| Embedding 模型 | `text-embedding-v4`（1024 维） |
| API 端点 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |

## 项目结构

```
qa_generate_v4/
├── generate_qa.py              # 主入口（手动 / 自动两种模式）
├── requirements.txt            # openai, openpyxl, numpy
├── qa_gen/                     # 核心包
│   ├── config.py               # LLM/Embedding 模型、API key、调用上限
│   ├── llm_client.py           # LLM + Embedding API 调用（指数退避）
│   ├── auto_config.py          # 【编辑此文件】批量生成目标列表
│   ├── auto_buckets.py         # 自动扫描 JSONL → 生成任务桶
│   ├── buckets.py              # 手动模式任务桶 + System Prompt
│   ├── generate.py             # 单条 QA 生成 + 负样本构造
│   ├── dedup.py                # Embedding 语义去重（同 section 桶内）
│   ├── gold.py                 # F 列子串定位 + G 列回填 + 余弦相似度
│   ├── validate.py             # §9 校验（chunk_id 存在性 / 子串匹配）
│   ├── writer.py               # 输出 xlsx + run_log.md
│   └── data_io.py              # JSONL 加载 + 文本归一化
├── data/                       # 保险文档（不纳入 git）
├── pilot_samples.json          # 手工标注样例（安达试点）
├── pilot_samples.xlsx          # 手工标注样例（Excel 版）
├── validation_report.md        # 校验报告
└── human_review_checklist.md   # 人工审核清单
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 设置 API Key

```bash
export DASHSCOPE_API_KEY="你的阿里云百炼 API Key"
```

### 3. 编辑批量目标

编辑 `qa_gen/auto_config.py`，配置要生成 QA 的 JSONL 文档列表：

```python
JSONL_TARGETS = [
    ("data/安达/Chubb_常見疾病指引_paged.jsonl", 20),
    ("data/安达/Chubb_Manual ..._paged.jsonl", 20),
    ("data/安盛/愛唯守危疾保障_产品彩页_paged.jsonl", 20),
    # ...
]
```

### 4. 运行

```bash
# 自动批量模式（推荐）— 按 auto_config.py 逐文档生成
python generate_qa.py --auto

# 手动模式 — 使用 buckets.py 硬编码任务桶
python generate_qa.py
```

输出文件在 `./output/` 目录下，每个文档生成一个 `_QA测评集.xlsx`。

## 工作流总览

```
PDF → JSONL (paged, 含 chunk_id + 页码)
  → generate_qa.py --auto (LLM 出题 + Embedding 去重)
    → _QA测评集.xlsx (含 question / answer / supporting_text / gold_chunk_ids)
      → 人工审核 + 补充 key_facts
        → 最终 JSONL 评测集
```

## 运行日志

每次运行后会在 `./output/run_log.md` 生成详细日志，包括：

- LLM / Embedding 调用次数和错误数
- 去重删除条数
- 校验问题列表
- 分布统计（intent / answer_type / section_title）

## 配置说明

| 配置项 | 默认值 | 位置 |
|---|---|---|
| LLM 模型 | `qwen-plus` | `config.py` |
| Embedding 模型 | `text-embedding-v4` | `config.py` |
| LLM 调用上限 | 200 | `config.py` |
| Embedding 批数上限 | 10 | `config.py` |
| 去重相似度阈值 | 0.85 | `config.py` |
| question 最大字数 | 35-50 字 | `buckets.py` / `generate.py` |
| 负样本数/文档 | 4 | `auto_config.py` |
| 同 section 最大出题数 | 3 | `auto_config.py` |

## Schema（xlsx 输出列）

| 列 | 字段 | 说明 |
|---|---|---|
| A | category | 分类（产品 / 健康核保 / 运营） |
| B | question | 问题（简体，口语化，≤50 字） |
| C | answer | 预期回答 |
| D | document | 来源文档名 |
| E | page | 源码页码 |
| F | supporting_text | 支撑原文（必须是某 chunk 的逐字子串） |
| G | gold_chunk_ids | 出处 chunk_id（分号分隔） |
| H | answer_type | single_fact / multi_chunk / table_lookup / unanswerable |
| I | intent | 意图分类（查详情 / 要数字 / 查核保 / 操作指引 / …） |

## JSONL 评测集格式

每条记录包含：

```json
{
  "id": 1,
  "question": "…",
  "reference_answer": "…",
  "company": "安达",
  "product_name": "…",
  "answer_type": "single_fact",
  "intent": "查核保",
  "gold_evidence": [{ "page": 8, "text_snippet": "…" }],
  "gold_chunk_ids": ["…"],
  "key_facts": ["…", "…"],
  "relevance_level": "essential"
}
```
