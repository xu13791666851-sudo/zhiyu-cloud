"""
知域 - 文献管理模块

负责文献相关的全部业务逻辑：
- 文献推荐（基于关键词匹配和检索片段）
- 文献上传（PDF/TXT/MD 解析 → 分块 → 写入知识库）
- 知识库统计、搜索、持久化
"""

import os
import re
import json
import html as html_module

from config import KNOWLEDGE_BASE


# ==================== 文献推荐 ====================

def recommend_docs(query, chunks):
    """基于检索片段生成文献推荐 HTML。"""
    if not chunks:
        return ""

    stopwords = {"的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
                 "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
                 "会", "着", "没有", "看", "好", "自己", "这", "那", "什么", "吗",
                 "哪", "哪些", "如何", "怎样", "为什么", "关于", "被", "从", "为",
                 "以", "对", "能", "而", "与", "其", "中", "已", "还", "把", "让",
                 "用", "所", "之", "但", "因", "更", "最", "各", "这些", "那些"}
    query_chars = [c for c in query if c not in stopwords and c.strip()]

    doc_scores = {}
    for c in chunks:
        doc = c.get("doc", "未知来源")
        content = c.get("content", "")

        kw_score = sum(content.count(c) for c in query_chars)

        if doc not in doc_scores:
            doc_scores[doc] = {"chunk_count": 0, "kw_score": 0, "snippet": content[:100]}
        doc_scores[doc]["chunk_count"] += 1
        doc_scores[doc]["kw_score"] += kw_score

    ranked = sorted(doc_scores.items(), key=lambda x: (x[1]["kw_score"], x[1]["chunk_count"]), reverse=True)

    rec_items = ""
    for i, (doc, info) in enumerate(ranked[:5], 1):
        escaped_doc = html_module.escape(doc)
        snippet = html_module.escape(info["snippet"][:80].replace("\n", " "))
        if len(info["snippet"]) > 80:
            snippet += "..."

        reasons = []
        if info["kw_score"] >= 10:
            reasons.append("关键词高度匹配")
        if info["chunk_count"] >= 2:
            reasons.append(f"涉及 {info['chunk_count']} 个相关片段")
        if not reasons:
            reasons.append("内容相关")

        reason_str = "、".join(reasons)
        rec_items += f"""
        <div class="rec-item">
            <div class="rec-rank">{i}</div>
            <div class="rec-info">
                <div class="rec-doc">{escaped_doc}</div>
                <div class="rec-snippet">{snippet}</div>
                <div class="rec-reason">{reason_str}</div>
            </div>
        </div>"""

    return f"""
    <div class="insight-panel">
        <div class="insight-title">推荐文献</div>
        <div class="rec-list">
            {rec_items}
        </div>
    </div>"""


# ==================== 文献上传与解析 ====================

def upload_document(files):
    """接受上传文件（PDF/TXT/MD），提取文本、分块、追加到知识库。"""
    global KNOWLEDGE_BASE

    if not files:
        return "未选择任何文件。", build_doc_table(), get_kb_stats()[0], get_kb_stats()[1]

    added_docs = 0
    added_chunks = 0
    results = []

    for file in files:
        filename = file.name if hasattr(file, 'name') else str(file)
        basename = os.path.basename(filename)

        try:
            if basename.lower().endswith('.txt'):
                with open(filename, 'r', encoding='utf-8') as f:
                    text = f.read()
            elif basename.lower().endswith('.pdf'):
                text = extract_pdf_text(filename)
            elif basename.lower().endswith('.md'):
                with open(filename, 'r', encoding='utf-8') as f:
                    text = f.read()
            else:
                results.append(f"- {basename}：不支持该格式（仅支持 .txt / .pdf / .md）")
                continue

            if not text or len(text.strip()) < 20:
                results.append(f"- {basename}：文本内容过少或为空，已跳过")
                continue

            chunks = chunk_text(text, basename)
            if not chunks:
                results.append(f"- {basename}：分块后无有效内容，已跳过")
                continue

            KNOWLEDGE_BASE.extend(chunks)
            added_docs += 1
            added_chunks += len(chunks)
            results.append(f"- {basename}：成功导入 {len(chunks)} 个知识片段")

            save_knowledge_base()

        except Exception as e:
            results.append(f"- {basename}：处理失败 - {str(e)}")

    summary = f"上传完成：共新增 {added_docs} 篇文献、{added_chunks} 个知识片段\n\n" + "\n".join(results)
    return summary, build_doc_table(), get_kb_stats()[0], get_kb_stats()[1]


def extract_pdf_text(filepath):
    """从 PDF 文件中提取文本。"""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(filepath)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except ImportError:
        try:
            import subprocess
            result = subprocess.run(
                ['python', '-c',
                 f"""
import fitz; doc = fitz.open('{filepath}'); text = ''
for p in doc: text += p.get_text()
doc.close(); print(text)
"""],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception:
            pass
        raise RuntimeError("PDF 解析需要 PyMuPDF 库（fitz），请运行 pip install PyMuPDF")


def chunk_text(text, doc_name, chunk_size=500, overlap=80):
    """将文本按段落/句子分块，带重叠。"""
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    if not text:
        return []

    paragraphs = re.split(r'\n\n+', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= chunk_size:
            current_chunk = (current_chunk + "\n\n" + para).strip()
        else:
            if current_chunk:
                chunks.append({
                    "content": current_chunk,
                    "doc": doc_name,
                    "similarity": 0.0
                })
            if len(para) > chunk_size:
                sentences = re.split(r'(?<=[。！？；\.\!\?;])', para)
                sub_chunk = ""
                for sent in sentences:
                    if len(sub_chunk) + len(sent) <= chunk_size:
                        sub_chunk += sent
                    else:
                        if sub_chunk:
                            chunks.append({
                                "content": sub_chunk.strip(),
                                "doc": doc_name,
                                "similarity": 0.0
                            })
                        sub_chunk = sent
                current_chunk = sub_chunk
            else:
                current_chunk = para

    if current_chunk.strip():
        chunks.append({
            "content": current_chunk.strip(),
            "doc": doc_name,
            "similarity": 0.0
        })

    return chunks


# ==================== 知识库统计与搜索 ====================

def save_knowledge_base():
    """将知识库持久化到磁盘。"""
    global KNOWLEDGE_BASE
    kb_path = os.path.join(os.path.dirname(__file__), "knowledge_base.json")
    with open(kb_path, "w", encoding="utf-8") as f:
        json.dump(KNOWLEDGE_BASE, f, ensure_ascii=False, indent=2)


def get_kb_stats():
    """获取知识库统计数据（文献数、片段数）。"""
    if not KNOWLEDGE_BASE:
        return "知识库暂无数据", "0", "0"

    docs = set()
    for chunk in KNOWLEDGE_BASE:
        doc = chunk.get("doc", "")
        if doc:
            docs.add(doc)

    total_chunks = len(KNOWLEDGE_BASE)
    total_docs = len(docs)

    return f"{total_docs} 篇文献", f"{total_chunks} 个知识片段", total_chunks, total_docs


def build_doc_table():
    """构建文献列表的 Markdown 表格。"""
    if not KNOWLEDGE_BASE:
        return "知识库暂无数据。"

    doc_map = {}
    for chunk in KNOWLEDGE_BASE:
        doc = chunk.get("doc", "未知来源")
        content = chunk.get("content", "")
        if doc not in doc_map:
            doc_map[doc] = {"count": 0, "total_chars": 0}
        doc_map[doc]["count"] += 1
        doc_map[doc]["total_chars"] += len(content)

    lines = "| 序号 | 文献名称 | 知识片段数 | 总字符数 |\n|------|----------|-----------|----------|\n"
    for i, (doc, info) in enumerate(sorted(doc_map.items()), 1):
        lines += f"| {i} | {doc} | {info['count']} | {info['total_chars']:,} |\n"

    return lines


def search_docs(keyword):
    """按关键词搜索知识库内容。"""
    if not keyword or not keyword.strip():
        return build_doc_table()

    if not KNOWLEDGE_BASE:
        return "知识库暂无数据。"

    keyword = keyword.strip()
    matched_chunks = []
    for chunk in KNOWLEDGE_BASE:
        content = chunk.get("content", "")
        if keyword in content:
            matched_chunks.append(chunk)

    if not matched_chunks:
        return f"未找到包含「{keyword}」的内容。"

    lines = f"找到 {len(matched_chunks)} 个包含「{keyword}」的知识片段：\n\n"
    lines += "| 序号 | 来源文献 | 内容摘要（前120字） |\n|------|----------|---------------------|\n"
    for i, chunk in enumerate(matched_chunks[:20], 1):
        doc = chunk.get("doc", "未知来源")
        content = chunk.get("content", "")[:120].replace("\n", " ").replace("|", "\\|")
        lines += f"| {i} | {doc} | {content}... |\n"

    if len(matched_chunks) > 20:
        lines += f"\n> 还有 {len(matched_chunks) - 20} 条结果未显示"

    return lines
