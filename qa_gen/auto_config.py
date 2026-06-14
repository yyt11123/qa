# -*- coding: utf-8 -*-
"""自动批量生成配置 —— 编辑此文件选择要生成 QA 的 JSONL 文档。

格式: (jsonl_path, max_questions)
  - jsonl_path: 相对项目根目录的 paged.jsonl 路径
  - max_questions: 该文档最多生成的 QA 条数（不含负样本）
"""

# ---- 用户编辑区域 ----------------------------------------
JSONL_TARGETS = [
    # === 安达 ===
    ("data/安达/Chubb_Manual 高資產業務人壽保障產品指引 (CH) - Clean_2024Oct_paged.jsonl", 20),
    ("data/安达/Chubb_常見疾病指引_paged.jsonl", 20),

    # === 安盛 ===
    ("data/安盛/愛唯守危疾保障_产品彩页_paged.jsonl", 20),
    ("data/安盛/安盛挚汇_产品彩页_paged.jsonl", 15),
    # ("data/安盛/保單行政手冊 _FI202409_paged.jsonl", 10),
    # ("data/安盛/安盛_理財顧問手冊_投保指引_202501 (1)_paged.jsonl", 10),

    # === 保诚 ===
    # ("data/保诚/EGC Product Manual v14.1 (Oct2024)_paged.jsonl", 15),
    # ("data/保诚/「自主未來」保障計劃產品資料_2023_04_paged.jsonl", 15),
    # ("data/保诚/雋富多元貨幣资料册_2022_12_paged.jsonl", 15),

    # === 宏利 ===
    # ("data/宏利/宏摯傳承保障計劃_产品彩页_paged.jsonl", 15),
    # ("data/宏利/活耀人生危疾保-产品手册_paged.jsonl", 15),

    # === 富卫 ===
    # ("data/富卫/盈聚·天下壽險計劃_产品彩页_paged.jsonl", 15),

    # === 立桥 ===
    # ("data/立橋/立桥运营指引手册_2023_08_09_paged.jsonl", 10),

    # === 太平 ===
    # ("data/太平/中國太平人壽保險(香港)有限公司投保指引（2024版）_paged.jsonl", 10),

    # 更多文档按需添加...
]
# ---------------------------------------------------------

# 负样本配置：每个文档自动生成的负样本数量
NEGATIVE_COUNT = 4

# 同 section_title 下最多取几个 chunk（避免同一节出题过度集中）
MAX_CHUNKS_PER_SECTION = 3

# QA 级 chunk 最短内容长度（字符）
MIN_CONTENT_LENGTH = 30

# 排除的 chunk_type（不是实质性内容）
EXCLUDED_CHUNK_TYPES = {"doc_summary", "section"}

# ── doc_type → intent 轮转列表 ──
# 顺序即为轮转顺序，保证同一文档内题型多样
INTENT_MAP = {
    "product_brochure":  ["查详情", "要数字", "查详情", "查覆盖", "资格门槛",
                          "问优惠", "要数字", "查详情", "查覆盖"],
    "underwriting_rule": ["查核保", "资格门槛", "查详情", "查核保", "操作指引"],
    "claim_guide":       ["理赔", "理赔", "操作指引", "查详情"],
    "policy_terms":      ["查详情", "资格门槛", "要数字", "查详情", "操作指引"],
    "other":             ["操作指引", "操作指引", "查详情", "缴费"],
}

# ── doc_type → category ──
CATEGORY_MAP = {
    "product_brochure": "产品",
    "policy_terms":     "产品",
}
DEFAULT_CATEGORY = "运营"

# ── doc_type → 负样本模板 ──
# {product} 会被替换为实际产品名
NEGATIVE_TEMPLATES = {
    "product_brochure": [
        "{product}现在有预缴保费优惠吗？力度多少？",
        "{product}和保诚的同类产品哪个更好？",
        "35岁女性买50万保额，{product}一年保费多少？",
        "{product}第10年退保现金价值是多少？",
        "{product}理赔多久到账，需要几个工作日？",
        "{product}在哪里可以投保，有线下门店吗？",
    ],
    "underwriting_rule": [
        "有乙肝小三阳，买{product}会被拒保吗？",
        "70岁老人能买{product}吗？",
        "{product}和友邦的核保规则对比",
        "对比各公司{product}的核保要求",
    ],
    "claim_guide": [
        "{product}理赔多久到账？",
        "对比各公司的理赔时效？",
    ],
    "policy_terms": [
        "{product}对比其他公司有什么优势？",
        "{product}有没有预缴优惠？",
        "给我{product}的完整费率表",
    ],
    "other": [
        "对比各公司的{product}有什么区别？",
        "为什么{product}流程这么复杂，能不能简化？",
    ],
}
