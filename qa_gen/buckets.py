# -*- coding: utf-8 -*-
"""任务桶定义（§4 配额，覆盖 §5 的多个 section_title）+ 负样本桶 + 系统 prompt。"""

# -------- 任务桶定义（§4 配额，覆盖 §5 的多个 section_title） --------
# 每个任务：intent / sub_intent / category / answer_type_hint / chunk_ids / hint
BUCKETS = [
    # === A 查详情：保障范围/特性 (产品, 14) ===
    {"key":"A1", "intent":"查详情", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0003","9260cfa4_chunk_0013"],
     "hint":"3大早期风险状况（心肌病早期擴張型 / 大腸息肉腺瘤性 / 原位癌）的范围"},
    {"key":"A2", "intent":"查详情", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0013"],
     "hint":"早期风险守护保险赔偿支付次数（每种早期风险只赔1次，合共2次）"},
    {"key":"A3", "intent":"查详情", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0008"],
     "hint":"持续癌症保险赔偿是什么 / 怎么赔（每月保额5%、长达100个月）"},
    {"key":"A4", "intent":"查详情", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0009","9260cfa4_chunk_0012"],
     "hint":"严重认知障碍症照顾者年金（每年保额6%，至100岁）"},
    {"key":"A5", "intent":"查详情", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0014"],
     "hint":"严重疾病多重保险赔偿的覆盖（直至85岁，每次100%保额）"},
    {"key":"A6", "intent":"查详情", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0015","9260cfa4_chunk_0017"],
     "hint":"持续癌症保险赔偿的等候期（短至1年）/ 选项条件"},
    {"key":"A7", "intent":"查详情", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0025"],
     "hint":"教育特殊支援（6-18岁、保额5%、只索偿1次）"},
    {"key":"A8", "intent":"查详情", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0032"],
     "hint":"愛滿途支援計劃 / 一系列增值服务（预防 / 治疗 / 康复）"},
    {"key":"A9", "intent":"查详情", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0031"],
     "hint":"增值權益附加條款（额外保费 + 保额每年自动增加）"},
    {"key":"A10","intent":"查详情", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0031","9260cfa4_chunk_0206"],
     "hint":"延長寬限期保障（特定事件：结婚/生育/失业/离婚 → 最多365日）"},
    {"key":"A11","intent":"查详情", "category":"产品", "answer_type":"multi_chunk",
     "chunk_ids":["9260cfa4_chunk_0028","9260cfa4_chunk_0192"],
     "hint":"额外保障规则（首10个保单年度内额外50%保额）"},
    {"key":"A12","intent":"查详情", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0027"],
     "hint":"未成年保单的额外保障（终身）"},
    {"key":"A13","intent":"查详情", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0026"],
     "hint":"一站式财富累积（保证现金价值、终期红利）"},
    {"key":"A14","intent":"查详情", "category":"产品", "answer_type":"multi_chunk",
     "chunk_ids":["9260cfa4_chunk_0203","9260cfa4_chunk_0205","9260cfa4_chunk_0206"],
     "hint":"保单持有人身故保费豁免的核心条件（持有人保单日期年龄50岁或以下、生效满2年、75岁或之前身故）"},

    # === B 要数字 (产品, 8) ===
    {"key":"B1","intent":"要数字", "category":"产品", "answer_type":"table_lookup",
     "chunk_ids":["9260cfa4_chunk_0007"],
     "hint":"严重疾病多重保险赔偿合共最多多少次（连同严重疾病保险赔偿合共高达9次）"},
    {"key":"B2","intent":"要数字", "category":"产品", "answer_type":"table_lookup",
     "chunk_ids":["9260cfa4_chunk_0007"],
     "hint":"癌症最多索偿几次（最多5次）"},
    {"key":"B3","intent":"要数字", "category":"产品", "answer_type":"table_lookup",
     "chunk_ids":["9260cfa4_chunk_0007"],
     "hint":"心脏病发作及中风最多索偿几次（最多2次）"},
    {"key":"B4","intent":"要数字", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0008","9260cfa4_chunk_0174"],
     "hint":"持续癌症保险赔偿每月赔多少（每月保额的5%）"},
    {"key":"B5","intent":"要数字", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0008","9260cfa4_chunk_0174"],
     "hint":"持续癌症保险赔偿最长多少个月（长达100个月）"},
    {"key":"B6","intent":"要数字", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0009","9260cfa4_chunk_0012"],
     "hint":"认知障碍症照顾者年金每年多少（保额的6%）"},
    {"key":"B7","intent":"要数字", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0009","9260cfa4_chunk_0012"],
     "hint":"认知障碍症照顾者年金支付到多少岁（100岁）"},
    {"key":"B8","intent":"要数字", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0014"],
     "hint":"总保障最高多少（保额1000%）"},

    # === C 资格门槛 (产品, 4) ===
    {"key":"C1","intent":"资格门槛", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0170"],
     "hint":"非严重疾病保险赔偿的货币上限（港元/澳门币/美元三种货币的具体数字）"},
    {"key":"C2","intent":"资格门槛", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0215"],
     "hint":"澳门保单的货币选择（澳门币或其他可供选择的货币）"},
    {"key":"C3","intent":"资格门槛", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0223"],
     "hint":"暂停缴付保费的后果（宽限期31日 / 保单可能终止）"},
    {"key":"C4","intent":"资格门槛", "category":"产品", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0203"],
     "hint":"持有人身故保费豁免的年龄要求（保单日期当日50岁或以下）"},

    # === D 查覆盖：受保疾病 (健康核保, 5) ===
    {"key":"D1","intent":"查覆盖", "category":"健康核保", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0013","9260cfa4_chunk_0004"],
     "hint":"产品总共保障多少种疾病（135种非严重至严重疾病）"},
    {"key":"D2","intent":"查覆盖", "category":"健康核保", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0004"],
     "hint":"严重疾病多少种（63种）"},
    {"key":"D3","intent":"查覆盖", "category":"健康核保", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0004"],
     "hint":"非严重疾病多少种（72种）"},
    {"key":"D4","intent":"查覆盖", "category":"健康核保", "answer_type":"single_fact",
     "chunk_ids":["9260cfa4_chunk_0004","9260cfa4_chunk_0013"],
     "hint":"重大手术覆盖多少种（51种）"},
    {"key":"D5","intent":"查覆盖", "category":"健康核保", "answer_type":"table_lookup",
     "chunk_ids":["9260cfa4_chunk_0011","9260cfa4_chunk_0087"],
     "hint":"儿童非严重疾病多少种（15种）"},

    # === E 分人群保障 (产品, 3) ===
    {"key":"E1","intent":"查详情", "category":"产品", "answer_type":"multi_chunk",
     "chunk_ids":["9260cfa4_chunk_0010","9260cfa4_chunk_0021"],
     "hint":"愛寶保对孕妇 / 宝宝的保障（孕期18周起、妊娠并发症保障、产后抑郁）"},
    {"key":"E2","intent":"查详情", "category":"产品", "answer_type":"multi_chunk",
     "chunk_ids":["9260cfa4_chunk_0012"],
     "hint":"年长人士的保障（中度严重至严重认知障碍症 / 早期检测）"},
    {"key":"E3","intent":"查详情", "category":"产品", "answer_type":"multi_chunk",
     "chunk_ids":["9260cfa4_chunk_0011","9260cfa4_chunk_0025"],
     "hint":"儿童及照顾者的保障（15种儿童非严重疾病 / 教育特殊支援）"},
]

# 负样本（拒答）
NEG_BUCKETS = [
    {"key":"F1", "topic":"预缴保费优惠 / 折扣力度",
     "question":"爱唯守现在有预缴保费优惠吗？力度多少？"},
    {"key":"F2", "topic":"与保诚等他司危疾产品对比",
     "question":"爱唯守和保诚的危疾产品哪个保得多？"},
    {"key":"F3", "topic":"具体年龄 / 保额下的保费报价",
     "question":"35岁女性买50万保额，爱唯守一年保费多少？"},
    {"key":"F4", "topic":"退保现金价值具体表",
     "question":"爱唯守第10年退保现金价值是多少？"},
    {"key":"F5", "topic":"理赔时效 / 多少个工作日到账",
     "question":"爱唯守理赔多久到账，需要几个工作日？"},
    {"key":"F6", "topic":"在哪里购买 / 投保门店地址",
     "question":"爱唯守在哪里可以投保，有线下门店吗？"},
]


# -------- LLM Prompt 模板 --------
SYS_PROMPT = (
    "你是保险测评 QA 出题助手。基于「我提供的若干 chunk 原文」生成 1 条 QA。\n"
    "硬性约束（违反即视为失败）：\n"
    "1) 只能根据我给出的原文作答，禁止使用模型自身知识或跨文档补充；\n"
    "2) 问题写【简体中文】、短问、关键词式，少于 30 字（最多 35 字），一题一问；\n"
    "3) 问题以「爱唯守」或「安盛爱唯守」起手；问题不要带客户场景（除非任务明确要求）；\n"
    "4) **question 中严禁出现括号（）()或任何答案/提示内容**：题干只能是问题本身，不能携带括号备注、不能把答案的数字/百分比/术语直接复述进题干；\n"
    "5) answer 与 supporting_text 的字形必须与所选 chunk 的字形一致："
    "如果 chunk 内容是繁体则保持繁体，简体则简体；【不要做简繁互转】；\n"
    "6) supporting_text 必须是其中【某一个】chunk content 的【逐字子串】（不要改字、不要拼接）；\n"
    "7) supporting_text 长度 30~120 字之间，刚好覆盖回答依据；\n"
    "8) answer 长度 15~80 字之间，可对原文做最小整理（保留数字/百分号/单位）；\n"
    "输出严格 JSON：{\"question\":\"...\",\"answer\":\"...\",\"supporting_text\":\"...\",\"primary_chunk_id\":\"...\"}。\n"
    "primary_chunk_id 取你 supporting_text 的来源 chunk 的 chunk_id（必须来自我列出的 chunk_ids）。"
)
