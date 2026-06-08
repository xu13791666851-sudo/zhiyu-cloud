"""
知域 - 实体识别模块

负责从问答上下文中提取和展示实体：
- LLM 实体提取
- 实体信息聚合（从知识库片段中补充）
- 实体卡片 HTML 渲染
"""

import re
import json
import html as html_module

from openai import OpenAI

from config import HUNYUAN_API_KEY, HUNYUAN_BASE_URL


def extract_entities(query, answer, chunks):
    """使用 LLM 从问答上下文中提取命名实体。"""
    if not HUNYUAN_API_KEY or not chunks:
        return []

    client = OpenAI(api_key=HUNYUAN_API_KEY, base_url=HUNYUAN_BASE_URL)

    # 从检索片段中构建迷你上下文（取前 5 条，截断）
    ctx = ""
    for i, c in enumerate(chunks[:5]):
        ctx += f"[{c.get('doc','')}] {c.get('content','')[:200]}\n"

    prompt = f"""从以下问答和文献片段中提取核心实体。只提取以下类型的实体：
1. 建筑名称（如：国贸大厦、上海宾馆、白沙岭住宅区）
2. 人物名称（如：建筑师、城市规划师）
3. 地区/区域名（如：蛇口、罗湖、福田）
4. 机构/组织名（如：建设公司、设计院）

## 用户问题
{query}

## AI 回答
{answer[:800]}

## 文献片段
{ctx[:2000]}

请严格按以下 JSON 格式输出，不要输出其他内容：
[{{"name":"实体名","type":"建筑/人物/地区/机构","desc":"一句话描述（20字以内）"}}]

如果没有识别到实体，输出空数组 []。"""

    try:
        resp = client.chat.completions.create(
            model="hunyuan-turbos-latest",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        text = resp.choices[0].message.content.strip()
        # 从回复中提取 JSON 数组
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            entities = json.loads(match.group())
            # 按名称去重
            seen = set()
            unique = []
            for e in entities:
                n = e.get("name", "").strip()
                if n and n not in seen:
                    seen.add(n)
                    unique.append(e)
            return unique[:6]  # 最多 6 个实体
        return []
    except Exception:
        return []


def aggregate_entity_info(entity_name, chunks):
    """从知识库片段中聚合实体的相关信息。"""
    info_parts = []
    source_docs = set()
    for c in chunks:
        content = c.get("content", "")
        if entity_name in content:
            sentences = re.split(r'[。！？\n]', content)
            for sent in sentences:
                if entity_name in sent and len(sent.strip()) > 10:
                    info_parts.append(sent.strip())
                    source_docs.add(c.get("doc", ""))
                    break  # 每个片段取一句
            if len(info_parts) >= 3:
                break

    return info_parts[:3], list(source_docs)


def render_entity_cards(entities, chunks):
    """将实体信息渲染为带样式的 HTML 卡片。"""
    if not entities:
        return ""

    type_icons = {
        "建筑": "🏛️",
        "人物": "👤",
        "地区": "📍",
        "机构": "🏢",
    }

    cards_html = ""
    for e in entities:
        name = html_module.escape(e.get("name", ""))
        etype = e.get("type", "建筑")
        desc = html_module.escape(e.get("desc", ""))
        icon = type_icons.get(etype, "📌")

        # 从检索片段中补充信息
        info_parts, src_docs = aggregate_entity_info(name, chunks)
        detail_html = ""
        if info_parts:
            detail_items = "".join(f"<li>{html_module.escape(p)}</li>" for p in info_parts[:2])
            detail_html = f"<ul style='margin:0.4rem 0 0 0;padding-left:1rem;font-size:0.78rem;color:#555;line-height:1.6;'>{detail_items}</ul>"

        source_tag = ""
        if src_docs:
            source_tag = f"<span style='font-size:0.7rem;color:#aaa;'>来源：{'、'.join(html_module.escape(d) for d in src_docs[:2])}</span>"

        cards_html += f"""
        <div class="entity-card">
            <div class="entity-header">
                <span class="entity-icon">{icon}</span>
                <span class="entity-name">{name}</span>
                <span class="entity-type">{html_module.escape(etype)}</span>
            </div>
            <div class="entity-desc">{desc}</div>
            {detail_html}
            {source_tag}
        </div>"""

    return f"""
    <div class="insight-panel">
        <div class="insight-title">相关实体</div>
        <div class="entity-grid">
            {cards_html}
        </div>
    </div>"""
