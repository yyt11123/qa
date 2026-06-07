# -*- coding: utf-8 -*-
"""配置常量 + 全局 _stats + log_event + OpenAI client。
其他模块统一从此处 import，不要重新定义或拷贝 _stats / client。"""
import os

from openai import OpenAI

# -------- 配置 --------
INPUT_JSONL = "愛唯守危疾保障_产品彩页_paged(1).jsonl"
OUT_DIR     = "./output"
OUT_XLSX    = os.path.join(OUT_DIR, "愛唯守_QA测评集.xlsx")
OUT_LOG     = os.path.join(OUT_DIR, "run_log.md")
DOC_NAME    = "愛唯守危疾保障.pdf"

LLM_MODEL = "qwen-plus"
EMB_MODEL = "text-embedding-v4"

# 上限（§12 防空转）
MAX_LLM_CALLS  = 200
MAX_EMB_BATCHES = 10
MAX_RETRIES_PER_ITEM = 2
DEDUP_SIM_THRESHOLD = 0.85

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# 调用计数（全局）
_stats = {
    "llm_calls": 0, "llm_errors": 0,
    "emb_batches": 0, "emb_errors": 0,
    "retries": 0, "dropped": 0,
    "log_assumptions": [],
    "log_events": [],
}

def log_event(msg):
    print(msg)
    _stats["log_events"].append(msg)
