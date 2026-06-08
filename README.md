# qa_generate_v3 — 保险 RAG 测评数据集构建与评测

从单个产品文档（已切分好的 `.jsonl` chunk 文件）自动生成一套 **RAG 测评 QA 集**，
输出为 `.xlsx`，再将其转为标准 **JSONL 评测数据集**，最终提供一套 **评测脚本骨架**
（检索 Recall@k / MRR + 生成 LLM-as-judge + 拒答准确率）。

当前数据源为安盛「愛唯守危疾保障」产品彩页，共 31 条 QA（25 条可答 + 6 条超纲拒答负样本）。

## 目录结构

```
qa_generate_v3/
├── generate_qa.py              # 入口：编排各模块、运行主流程
├── qa_gen/                     # 核心逻辑包（QA 生成）
│   ├── config.py               # 配置常量 + OpenAI client + 全局 _stats + log_event
│   ├── llm_client.py           # gen() / embed() —— API 调用（含退避、批量切分）
│   ├── data_io.py              # 加载 jsonl、文本归一化
│   ├── gold.py                 # gold_chunk_ids 匹配、余弦相似度
│   ├── buckets.py              # 出题任务桶 BUCKETS / 负样本 NEG_BUCKETS / 系统 prompt
│   ├── generate.py             # 单条 QA 生成、负样本构造、问题清洗
│   ├── dedup.py                # embedding 语义去重
│   ├── validate.py             # 校验
│   └── writer.py               # 写出 xlsx / 运行日志
├── convert_xlsx_to_jsonl.py    # xlsx → 标准 JSONL（带校验）
├── eval/                       # 评测模块
│   ├── qa_dataset.jsonl        # 标准 JSONL 评测数据集（31 条）
│   ├── evaluate.py             # 评测脚本骨架（检索 + 生成 + 拒答）
│   └── results.json            # 评测结果输出
├── report.md                   # 真实顾问提问画像分析（出题依据）
├── requirements.txt
├── .gitignore
└── 愛唯守危疾保障_产品彩页_paged(1).jsonl   # 数据源（已切分 chunk）
```

## 工作流概览

```
┌─────────────────────┐      ┌─────────────────────────┐      ┌───────────────────┐
│  1. QA 生成          │ ───→ │  2. xlsx → JSONL 转换    │ ───→ │  3. 评测           │
│  generate_qa.py      │      │  convert_xlsx_to_jsonl.py│      │  eval/evaluate.py  │
│                       │      │                          │      │                    │
│  产出: .xlsx (31条)   │      │  产出: eval/qa_dataset.   │      │  产出: eval/results. │
│                       │      │        jsonl (标准格式)   │      │        json (汇总)   │
└─────────────────────┘      └─────────────────────────┘      └───────────────────┘
```

---

## 第一步：QA 生成（generate_qa.py）

### 设计要点

- **贴合真实提问**：题目分布参照真实顾问提问画像（`report.md`），以「产品详情 / 具体数字 / 受保疾病覆盖 / 资格门槛」四类意图为主，问题为简体短问。
- **可测召回**：每条可答题的 `gold_chunk_ids` 精确指向含答案的 1~2 个 chunk（由支撑原文子串匹配确定，避免灌水虚高召回）。
- **可测置信度**：内置 6 条文档无法回答的负样本（`answer_type=unanswerable`），用于检验 RAG 是否正确拒答而非幻觉。
- **抗切分变化**：`text` 列保留原文出处，换不同切分的系统时可用文本重叠兜底判定召回。
- **生成 + 去重**：用 `qwen-plus` 基于 chunk 原文生成 QA，用 `text-embedding-v4` 做同主题语义去重。

### 环境要求

- Python 3.10+
- 阿里云百炼（DashScope）API Key，需有 `qwen-plus` 与 `text-embedding-v4` 权限

安装依赖：

```bash
pip install -r requirements.txt
```

### 配置 API Key

程序通过环境变量 `DASHSCOPE_API_KEY` 读取密钥（**切勿把密钥写进代码**）。

Windows PowerShell（当前会话有效）：

```powershell
$env:DASHSCOPE_API_KEY="你的key"
```

Linux / macOS：

```bash
export DASHSCOPE_API_KEY="你的key"
```

### 运行

```bash
python generate_qa.py
```

产出写入 `./output/`：

- `愛唯守_QA测评集.xlsx` —— QA 测评集（两行表头）
- `run_log.md` —— 运行日志（生成 / 去重 / 丢弃条数、分布、所做假设）

### xlsx 列说明

| 列 | 字段 | 含义 |
| -- | ---- | ---- |
| A  | 分类 | 产品 / 健康核保 |
| B  | question | 题目（简体短问） |
| C  | answers | 预期答案（繁体，源自原文） |
| D  | document | 来源 PDF 文件名 |
| E  | page | 所在页码 |
| F  | text/img/table | 支撑原文片段（grounding 依据） |
| G  | gold_chunk_ids | 含答案的 chunk_id（`;` 分隔） |
| H  | answer_type | single_fact / multi_chunk / table_lookup / unanswerable |
| I  | intent | 查详情 / 要数字 / 查覆盖 / 资格门槛 / 拒答 |

### 已知取舍

- 个别核心事实（如「总保障 1000%」「135 种疾病」）因原文含上标数字、`text` 逐字子串校验不通过，会被丢弃。这是「宁丢勿假」的设计，保证每条 gold 都可核验。
- 出题任务桶 `BUCKETS` 当前针对「愛唯守」手工定义，**换其他产品文档需另行调整**（自动建桶为后续工作）。

---

## 第二步：xlsx → JSONL 转换（convert_xlsx_to_jsonl.py）

将手工标注/生成的 `.xlsx` 测评集转换为标准 JSONL 评测数据集，供下游评测脚本使用。

### 运行

```bash
python convert_xlsx_to_jsonl.py
```

### JSONL 字段说明

| 字段 | 类型 | 说明 |
| ---- | ---- | ---- |
| id | int | 自增编号 |
| question | str | 问题文本 |
| reference_answer | str | 标准答案 |
| company | str | 公司名称（从源 jsonl 自动取） |
| product_name | str | 产品名称 |
| answer_type | str | single_fact / multi_chunk / table_lookup / unanswerable |
| intent | str | 意图分类 |
| gold_evidence | list | **评测核心依据**，每个元素 `{page, text_snippet}` |
| gold_chunk_ids | list | 仅供自查，评测不依赖 |

关键设计：
- **`gold_evidence`** 是判定检索命中的唯一依据（页码 + 原文片段），不依赖 chunk_id。
- 单 chunk 题目：`text_snippet` 取 xlsx 手工标注的精确原文，`page` 取标注页码。
- 多 chunk 题目：每条 evidence 取**各自 chunk 的 content** 作为 `text_snippet`，`page` 取各自的 `page_start`。
- `unanswerable` 的题目 `gold_evidence` 为空列表。

### 校验逻辑

转换时自动校验每条可答题：
1. `gold_chunk_ids` 是否存在于源 jsonl 中
2. `page` 是否在该 chunk 的 `page_start ~ page_end` 范围内
3. `text` 是否能在该 chunk 的 `content` 中找到（3-gram 字符重叠度 ≥ 50%）

校验不通过的行会打印出来供人工核对。

---

## 第三步：评测（eval/evaluate.py）

评测脚本骨架，当前用桩函数占位，接入真实 DashVector 检索 + LLM 生成时只需替换两个函数。

### 运行

```bash
python eval/evaluate.py \
    --dataset eval/qa_dataset.jsonl \
    --output eval/results.json \
    --top-k 10 \
    --threshold 0.6
```

参数说明：

| 参数 | 默认值 | 说明 |
| ---- | ------ | ---- |
| `--dataset` | `eval/qa_dataset.jsonl` | QA 评测数据集路径 |
| `--output` | `eval/results.json` | 评测结果输出路径 |
| `--top-k` | `10` | 检索返回的 Top-K 数量 |
| `--threshold` | `0.6` | 检索命中的 3-gram 字符重叠阈值 |

### 评测维度

#### 检索指标（已实现）

- **Recall@K**（K=1, 3, 5, 10）：Top-K 中至少命中一条 gold_evidence 的题目占比
- **MRR**（Mean Reciprocal Rank）：第一个命中 chunk 的排名的倒数均值
- **命中判定**：`gold.page == chunk.page` **且** `gold.text_snippet` 与 `chunk.text` 的 3-gram 重叠度 ≥ 阈值

#### 生成指标（占位）

- **LLM-as-judge** 接口留好（`evaluate_generation()`），需接入真实模型评估：
  - correctness：回答事实是否与标准答案一致（1-5）
  - faithfulness：回答是否严格基于原文，无编造（1-5）
  - completeness：是否覆盖所有关键信息点（1-5）
- 代码中有完整的 prompt 模板和 TODO 注释

#### 拒答指标（已实现）

- 对 `unanswerable` 题目，用关键词匹配判断 RAG 是否正确表示「资料中查不到」
- 覆盖简繁体双语模式

### 接入真实系统

只需替换 `eval/evaluate.py` 中的两个桩函数：

```python
def retrieve_stub(question: str, top_k: int = 10) -> list[dict]:
    """
    替换为：调用 DashVector embedding 检索，返回 Top-K chunks。
    返回格式: [{page: int, text: str, score: float}, ...]
    """

def generate_answer_stub(question: str, retrieved_chunks: list[dict]) -> str:
    """
    替换为：拼接 retrieved_chunks 为 context，调用 LLM 生成最终回答。
    返回格式: str
    """
```

其余评测逻辑（命中判定、指标计算、结果汇总）无需修改。

### 评测结果样例

```json
{
  "summary": {
    "total_questions": 31,
    "answerable": 25,
    "unanswerable": 6,
    "retrieval": {
      "MRR": 0.8500,
      "Recall@1": 0.8000,
      "Recall@3": 0.8800,
      "Recall@5": 0.9200,
      "Recall@10": 0.9600
    },
    "generation": { "method": "LLM-as-judge (TODO: 接入真实模型)" },
    "refusal_accuracy": 1.0000
  }
}
```

---

## 依赖

```
openai>=1.0.0        # DashScope 兼容 OpenAI SDK
openpyxl>=3.1.0      # xlsx 读写
numpy>=1.24.0        # 数值计算
```
