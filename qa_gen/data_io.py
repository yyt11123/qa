# -*- coding: utf-8 -*-
"""数据加载 & 文本归一化。"""
import json
import re


# -------- 数据加载 --------
def load_chunks(path):
    chunks = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    by_id = {c["chunk_id"]: c for c in chunks}
    return chunks, by_id


# -------- F 列子串校验（去空白后比对） --------
def _norm(s):
    if s is None:
        return ""
    return re.sub(r"\s+", "", str(s))
