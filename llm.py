"""
知域 - LLM 调用模块

负责与腾讯混元大模型的所有交互：
- 问答生成（含多轮对话上下文）
- Prompt 模板管理
"""

import re

from openai import OpenAI

from config import HUNYUAN_API_KEY, HUNYUAN_BASE_URL


def ask_llm(query, context_chunks, chat_history=None):
    """调用腾讯混元 LLM 生成回答，支持多轮对话上下文。"""
    if not HUNYUAN_API_KEY:
        return "API Key 未配置，请联系管理员。"

    client = OpenAI(api_key=HUNYUAN_API_KEY, base_url=HUNYUAN_BASE_URL)

    context_text = ""
    for i, chunk in enumerate(context_chunks):
        doc = chunk.get("doc", "未知来源")
        content = chunk.get("content", "")
        context_text += f"\n【文献片段 {i+1}】来源：{doc}\n{content}\n"

    system_prompt = f"""你是「知域」——深圳近现代建筑遗产领域的专业文献问答助手。

## 任务
严格根据【检索结果】回答用户问题。

## 规范
- 直接回答，不要寒暄引导语
- 「总—分」结构：1-2句核心结论 + 编号分点展开
- 每个论点紧接标注来源，格式：（来源：《文献名》）
- **不要在末尾添加"参考来源"或"参考文献"列表**——系统会自动添加
- 事实必须来自检索结果，不得编造；信息不足时明确说明"知识库中暂无此方面的记录"
- 涉及数据如实引用，不要估算
- 学术但易懂，客观中立

## 矛盾信息处理
- 若不同文献对同一问题有不同说法，**拆解各方观点**（说法A vs 说法B），分别标注各自来源
- 不要综合成一个模糊答案，而是让用户看到各方的底牌
- 若能判断可信度（一手文献 > 综述转引 > 未发表），给出简要建议

## 检索结果
{context_text}"""

    # 构建消息列表，加入多轮对话历史
    messages = [{"role": "system", "content": system_prompt}]

    if chat_history:
        # Gradio 6.x Chatbot history: [{"role": "user|assistant", "content": "..."}, ...]
        if isinstance(chat_history[0], dict):
            recent_history = chat_history[-20:]  # 最近 20 条消息
            for msg in recent_history:
                role = msg.get("role")
                content = msg.get("content")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
        else:
            # 兼容旧版 tuple 格式: [[user, assistant], ...]
            recent_history = chat_history[-10:]
            for turn in recent_history:
                if isinstance(turn, (list, tuple)) and len(turn) == 2:
                    user_msg, assistant_msg = turn
                    if user_msg:
                        messages.append({"role": "user", "content": user_msg})
                    if assistant_msg:
                        messages.append({"role": "assistant", "content": assistant_msg})

    # 加入当前提问
    messages.append({"role": "user", "content": query})

    try:
        response = client.chat.completions.create(
            model="hunyuan-turbos-latest",
            messages=messages,
            temperature=0.3,
            max_tokens=800,
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"调用失败：{str(e)}"


def clean_answer(answer):
    """清理 LLM 回答：去除自行生成的参考来源段落（系统会自动追加）。"""
    answer = re.sub(
        r'\n*(?:参考来源|参考文献|引用来源)[：:]\s*\n[\s\S]*?(?=\n\n|$)',
        '', answer
    )
    return answer.strip()


def append_sources(answer, chunks):
    """在回答末尾追加参考来源列表。"""
    sources = set()
    for c in chunks:
        if isinstance(c, dict):
            doc = c.get("doc", "")
            if doc:
                sources.add(doc)
    if sources:
        source_list = "\n".join(f"- {s}" for s in sorted(sources))
        answer += f"\n\n> **参考来源**：\n{source_list}"
    return answer
