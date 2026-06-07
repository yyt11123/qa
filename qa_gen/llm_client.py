# -*- coding: utf-8 -*-
"""LLM / Embedding API 调用，含指数退避。逻辑与原 generate_qa.py 完全一致。"""
import json
import re
import time

from qa_gen.config import (
    _stats,
    client,
    log_event,
    LLM_MODEL,
    EMB_MODEL,
    MAX_LLM_CALLS,
    MAX_EMB_BATCHES,
)


# -------- 工具：API 调用，含指数退避 --------
def gen(messages, retries=5):
    if _stats["llm_calls"] >= MAX_LLM_CALLS:
        log_event(f"[STOP] LLM 调用上限 {MAX_LLM_CALLS} 已达，跳过此次生成。")
        return None
    delay = 1.0
    for attempt in range(retries):
        try:
            _stats["llm_calls"] += 1
            r = client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
                temperature=0.4,
                timeout=60,
            )
            txt = r.choices[0].message.content
            try:
                return json.loads(txt)
            except json.JSONDecodeError:
                m = re.search(r"\{.*\}", txt, re.S)
                return json.loads(m.group(0)) if m else None
        except Exception as e:
            _stats["llm_errors"] += 1
            msg = str(e)
            unrecoverable = any(k in msg for k in ["401", "Authentication", "InvalidApiKey", "model not found", "ModelNotFound", "402", "PermissionDenied", "AccountFlowControl"])
            if unrecoverable:
                log_event(f"[FATAL] LLM 不可自愈错误：{msg}")
                raise
            log_event(f"[WARN] LLM 调用失败({attempt+1}/{retries}): {msg[:160]}; 退避 {delay:.1f}s")
            time.sleep(delay)
            delay *= 2
    log_event("[ERROR] LLM 多次重试仍失败，返回 None。")
    return None


def embed(texts, retries=5):
    """text-embedding-v4 每次最多 10 条，按 ≤10 切分批次循环调用，结果拼接。
    每个子批计入 emb_batches 并遵守 MAX_EMB_BATCHES。"""
    if not texts:
        return []
    BATCH_SIZE = 10
    all_vecs = []
    for s in range(0, len(texts), BATCH_SIZE):
        sub = texts[s:s + BATCH_SIZE]
        if _stats["emb_batches"] >= MAX_EMB_BATCHES:
            log_event(f"[STOP] embedding 批次上限 {MAX_EMB_BATCHES} 已达；剩余 {len(texts)-s} 条未向量化。")
            return None
        delay = 1.0
        sub_vecs = None
        for attempt in range(retries):
            try:
                _stats["emb_batches"] += 1
                r = client.embeddings.create(
                    model=EMB_MODEL, input=sub,
                    dimensions=1024, encoding_format="float", timeout=60,
                )
                sub_vecs = [d.embedding for d in r.data]
                break
            except Exception as e:
                _stats["emb_errors"] += 1
                msg = str(e)
                unrecoverable = any(k in msg for k in ["401", "Authentication", "InvalidApiKey", "model not found", "ModelNotFound", "402", "PermissionDenied"])
                if unrecoverable:
                    log_event(f"[FATAL] EMB 不可自愈错误：{msg}")
                    raise
                log_event(f"[WARN] EMB 调用失败({attempt+1}/{retries}): {msg[:160]}; 退避 {delay:.1f}s")
                time.sleep(delay)
                delay *= 2
        if sub_vecs is None:
            return None
        all_vecs.extend(sub_vecs)
    return all_vecs
