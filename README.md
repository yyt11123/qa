# qa_generate_v3 — 保险产品 RAG 测评 QA 生成器

从单个产品文档（已切分好的 `.jsonl` chunk 文件）自动生成一套 **RAG 测评 QA 集**，
输出为 `.xlsx`，每条 QA 带「标准答案 + 支撑原文 + gold_chunk_ids」，可用于评测 RAG 系统的
**检索召回率（Recall@k / MRR）** 与 **答案正确性 / 置信度（含拒答）**。

当前数据源为安盛「愛唯守危疾保障」产品彩页，共约 31 条 QA（含 6 条超纲拒答负样本）。

## 设计要点

- **贴合真实提问**：题目分布参照真实顾问提问画像（`report.md`），以「产品详情 / 具体数字 / 受保疾病覆盖 / 资格门槛」四类意图为主，问题为简体短问。
- **可测召回**：每条可答题的 `gold_chunk_ids` 精确指向含答案的 1~2 个 chunk（由支撑原文子串匹配确定，避免灌水虚高召回）。
- **可测置信度**：内置 6 条文档无法回答的负样本（`answer_type=unanswerable`），用于检验 RAG 是否正确拒答而非幻觉。
- **抗切分变化**：`supporting_text` 列保留原文出处，换不同切分的系统时可用文本重叠兜底判定召回。
- **生成 + 去重**：用 `qwen-plus` 基于 chunk 原文生成 QA，用 `text-embedding-v4` 做同主题语义去重。

## 环境要求

- Python 3.10+
- 阿里云百炼（DashScope）API Key，需有 `qwen-plus` 与 `text-embedding-v4` 权限

安装依赖：

```bash
pip install -r requirements.txt
```

## 配置 API Key

程序通过环境变量 `DASHSCOPE_API_KEY` 读取密钥（**切勿把密钥写进代码**）。

Windows PowerShell（当前会话有效）：

```powershell
$env:DASHSCOPE_API_KEY="你的key"
```

Linux / macOS：

```bash
export DASHSCOPE_API_KEY="你的key"
```

## 运行

```bash
python generate_qa.py
```

产出写入 `./output/`：

- `愛唯守_QA测评集.xlsx` —— QA 测评集（两行表头，与模板一致）
- `run_log.md` —— 运行日志（生成 / 去重 / 丢弃条数、分布、所做假设）

## 输出列说明

| 列  | 字段           | 含义                                                    |
| --- | -------------- | ------------------------------------------------------- |
| A   | 分类           | 产品 / 健康核保                                         |
| B   | question       | 题目（简体短问）                                        |
| C   | answers        | 预期答案（繁体，源自原文）                              |
| D   | document       | 来源 PDF 文件名                                         |
| E   | page           | 所在页码                                                |
| F   | text/img/table | 支撑原文片段（grounding 依据，answer 的来源句/表）      |
| G   | gold_chunk_ids | 含答案的 chunk_id（`;` 分隔）；**算召回率的核心字段**   |
| H   | answer_type    | single_fact / multi_chunk / table_lookup / unanswerable |
| I   | intent         | 查详情 / 要数字 / 查覆盖 / 资格门槛 / 拒答              |

## 目录结构

```
qa_generate_v3/
├── generate_qa.py            # 入口：编排各模块、运行主流程
├── qa_gen/                   # 核心逻辑包
│   ├── config.py             # 配置常量 + OpenAI client + 全局 _stats + log_event
│   ├── llm_client.py         # gen() / embed() —— API 调用（含退避、批量切分）
│   ├── data_io.py            # 加载 jsonl、文本归一化
│   ├── gold.py               # gold_chunk_ids 匹配、余弦相似度
│   ├── buckets.py            # 出题任务桶 BUCKETS / 负样本 NEG_BUCKETS / 系统 prompt
│   ├── generate.py           # 单条 QA 生成、负样本构造、问题清洗
│   ├── dedup.py              # embedding 语义去重
│   ├── validate.py           # §9 校验
│   └── writer.py             # 写出 xlsx / 运行日志
├── report.md                 # 真实顾问提问画像分析（出题依据）
├── requirements.txt
└── 愛唯守危疾保障_产品彩页_paged(1).jsonl   # 数据源（chunk）
```

## 已知取舍

- 个别核心事实（如「总保障 1000%」「135 种疾病」）因原文含上标数字、`supporting_text` 逐字子串校验不通过，会被丢弃。这是「宁丢勿假」的设计，保证每条 gold 都可核验。
- 出题任务桶 `BUCKETS` 当前针对「愛唯守」手工定义，**换其他产品文档需另行调整**（自动建桶为后续工作）。
