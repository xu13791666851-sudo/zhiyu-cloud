"""
知域 - UI 模块

负责 Gradio 前端的全部内容：
- CSS 样式
- JS 脚本（移动端适配、Tab 图标）
- Gradio Blocks 布局
- 事件绑定与回调编排
"""

import os
import tempfile
from datetime import datetime

import gradio as gr

from api import retrieve
from llm import ask_llm, clean_answer, append_sources
from entities import extract_entities, render_entity_cards
from docs import recommend_docs, upload_document, get_kb_stats, build_doc_table, search_docs


# ===================== CSS =====================

CUSTOM_CSS = """
/* ---- Global: full-width responsive layout ---- */
html, body {
    margin: 0 !important;
    padding: 0 !important;
    overflow-x: hidden !important;
    font-family: "Noto Serif SC", "Songti SC", "SimSun", serif !important;
    -webkit-font-smoothing: antialiased !important;
}
*, *::before, *::after {
    box-sizing: border-box !important;
}
.gradio-container,
.main,
.gr-app,
.app-container {
    max-width: 100% !important;
    width: 100% !important;
    margin: 0 !important;
    padding: 0 1.5rem 1.5rem 1.5rem !important;
    font-family: "Noto Serif SC", "Source Han Serif CN", "STSong", Georgia, serif !important;
    background: #fafafa !important;
    box-sizing: border-box !important;
    color: #1a1a2e !important;
}

.content-inner {
    max-width: 1200px;
    margin: 0 auto;
    width: 100%;
}

/* ---- Header bar ---- */
.top-header {
    text-align: center;
    padding: 1.5rem 0 1rem 0;
    border-bottom: 2px solid #1a1a2e;
    margin-bottom: 1.2rem;
}
.top-header h1 {
    font-size: 3.4rem !important;
    font-weight: 700 !important;
    color: #1a1a2e !important;
    letter-spacing: 0.15em;
    margin: 0 0 0.3rem 0 !important;
}
.top-header .tagline {
    font-size: 1rem !important;
    color: #666 !important;
    letter-spacing: 0.08em;
    margin: 0 !important;
}

/* ---- Tabs ---- */
.tabs { border: none !important; }
.tabs > .tab-wrapper {
    border-bottom: 2px solid #E8E8E8 !important;
    margin-bottom: 1.2rem !important;
}
.tabs > .tab-wrapper > .tab-container[role="tablist"] > button[role="tab"] {
    font-size: 1.25rem !important;
    font-weight: 500 !important;
    color: #666 !important;
    letter-spacing: 0.05em !important;
    padding: 0.7rem 1.5rem !important;
    border: none !important;
    background: none !important;
    font-family: "Noto Serif SC", "Source Han Serif CN", "STSong", Georgia, serif !important;
}
.tabs > .tab-wrapper > .tab-container[role="tablist"] > button[role="tab"].selected {
    color: #1a1a2e !important;
    border-bottom: 2px solid #1a1a2e !important;
    font-weight: 600 !important;
}

/* ---- Homepage hero ---- */
.hero-section {
    text-align: center;
    padding: 2rem 1rem 1.5rem 1rem;
}
.hero-section h2 {
    font-size: 1.75rem !important;
    color: #1a1a2e !important;
    margin-bottom: 0.8rem !important;
    letter-spacing: 0.1em;
}
.hero-section .hero-desc {
    font-size: 0.95rem !important;
    color: #555 !important;
    line-height: 1.8 !important;
}
.hero-section .demo-badge {
    display: inline-block;
    background: #1a1a2e;
    color: #fff;
    font-size: 0.75rem !important;
    padding: 0.2rem 0.8rem;
    border-radius: 3px;
    letter-spacing: 0.05em;
    margin-top: 1rem;
}

/* ---- Feature cards ---- */
.feature-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1rem;
    margin: 1.5rem 0 !important;
}
.feature-card {
    background: #fff !important;
    border: 1px solid #E8E8E8 !important;
    border-radius: 8px !important;
    padding: 1.5rem 1rem !important;
    text-align: center !important;
    transition: box-shadow 0.2s !important;
}
.feature-card:hover {
    box-shadow: 0 2px 8px rgba(0,0,0,0.08) !important;
}
.feature-card h3 {
    font-size: 1.25rem !important;
    color: #1a1a2e !important;
    margin: 0 0 0.5rem 0 !important;
    letter-spacing: 0.05em;
}
.feature-card p {
    font-size: 0.82rem !important;
    color: #777 !important;
    margin: 0 !important;
    line-height: 1.6 !important;
}

/* ---- Quick start section ---- */
.quickstart-section {
    background: #F5F5F5 !important;
    border-radius: 8px !important;
    padding: 1.5rem !important;
    margin-top: 1.5rem !important;
    border-left: 3px solid #1a1a2e !important;
}
.quickstart-section.demo-section {
    background: #FFFFFF !important;
    border-left: none !important;
}
.quickstart-section h3 {
    font-size: 1.25rem !important;
    color: #1a1a2e !important;
    margin: 0 0 0.8rem 0 !important;
    letter-spacing: 0.05em;
}
.quickstart-section ol {
    font-size: 0.88rem !important;
    color: #555 !important;
    line-height: 2 !important;
    padding-left: 1.5rem !important;
    margin: 0 !important;
}

/* ---- Quick Start button ---- */
.quick-start-btn-wrap {
    text-align: center;
    margin-top: 0.5rem !important;
    margin-bottom: 0.8rem !important;
}
#go-chat-btn {
    background: linear-gradient(135deg, #E8732A, #F59E0B) !important;
    color: #fff !important;
    font-size: 1.35rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em;
    padding: 0 !important;
    border-radius: 40px !important;
    border: none !important;
    cursor: pointer;
    transition: transform 0.15s, box-shadow 0.15s !important;
    box-shadow: 0 4px 14px rgba(232,115,42,0.30) !important;
    width: 400px !important;
    max-width: 88vw !important;
    height: 66px !important;
    min-height: 66px !important;
    margin: 0.8rem auto 0.5rem auto !important;
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    line-height: 1.3 !important;
}
#go-chat-btn span {
    color: #fff !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
}
#go-chat-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(232,115,42,0.50) !important;
    background: linear-gradient(135deg, #D4651E, #E88E08) !important;
    color: #fff !important;
}
#go-chat-btn:active { transform: translateY(0); }

:root {
    --color-bg: #fafafa;
    --color-surface: #ffffff;
    --color-primary: #1a1a2e;
    --color-muted: #666666;
    --color-muted-light: #777777;
    --color-border: #e8e8e8;
    --color-accent: #e8732a;
    --color-tab-inactive: #999999;
    --color-badge-bg: #eeeeee;
    --color-badge-text: #8d8c8c;
    --color-section-bg: #f5f5f5;
    --color-footer-text: #bbbbbb;
    --frame-max-width: 402px;
    --bottom-nav-height: 60px;
    --font-serif: "Noto Serif SC", "Songti SC", "SimSun", serif;
    --font-ui: system-ui, -apple-system, "Segoe UI", sans-serif;
}

*, *::before, *::after {
    box-sizing: border-box;
}

body {
    margin: 0;
    min-height: 100dvh;
    font-family: var(--font-serif);
    background: var(--color-bg);
    color: var(--color-primary);
    -webkit-font-smoothing: antialiased;
}

.gradio-container, .main, .gr-app, .app-container {
    max-width: 100%;
    width: 100%;
    margin: 0 auto;
    font-family: var(--font-serif);
    background: var(--color-bg);
    color: var(--color-primary);
    padding: 0 8px calc(var(--bottom-nav-height) + 16px) 8px !important;
    display: flex;
    flex-direction: column;
    gap: 6.4px;
}

.panel {
    display: none;
    flex-direction: column;
    gap: 6.4px;
    flex: 1;
    min-height: 0;
}

.panel.is-active {
    display: flex;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
}

/* 顶部标题区 */
.top-border, .top-header {
    border-bottom: 2px solid var(--color-primary);
    padding: 8px 0 6.8px 0;
    display: flex;
    flex-direction: column;
    gap: 3.19px;
}

.brand-title, .top-header h1 {
    margin: 0;
    text-align: center;
    font-size: 46px;
    font-weight: 700;
    letter-spacing: 3.12px;
    line-height: 1.2;
}

.brand-tagline, .top-header .tagline {
    margin: 0;
    text-align: center;
    font-size: 14px;
    font-weight: 400;
    color: var(--color-muted);
    letter-spacing: 0.922px;
}

/* Hero */
.hero-section {
    padding: 6.4px 3.2px 4.8px 3.2px;
}

.hero-section h2 {
    margin: 0;
    text-align: center;
    font-size: 17.6px;
    font-weight: 700;
    letter-spacing: 1.76px;
    line-height: 1.35;
}

.hero-badge-wrap {
    display: flex;
    justify-content: center;
    padding-top: 8px;
    min-height: 32.4px;
}

.demo-badge, .hero-badge {
    background: var(--color-badge-bg);
    color: var(--color-badge-text);
    font-size: 9px;
    letter-spacing: 0.6px;
    padding: 3.2px 12.8px;
    border-radius: 3px;
    line-height: 18px;
}

/* 功能网格 2×3 */
.feature-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    padding-top: 8px;
    width: 100%;
}

.feature-card {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: 6px;
    padding: 12px 10px;
    min-height: 110px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-items: stretch;
}

.feature-card h3 {
    margin: 0;
    text-align: center;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.656px;
}

.feature-card p {
    margin: 0;
    text-align: center;
    font-size: 12.5px;
    color: var(--color-muted-light);
    line-height: 1.5;
}

/* 如何使用 */
.quickstart-section, .block-howto {
    width: 100%;
    max-width: 359px;
    align-self: center;
    background: var(--color-section-bg);
    border-left: 3px solid var(--color-primary);
    border-radius: 6px;
    padding: 9.6px 8px 8px 11px;
    display: flex;
    flex-direction: column;
    gap: 3.8px;
}

.quickstart-section h3, .block-howto h3, .block-demo h3 {
    margin: 0;
    font-size: 13.1px;
    font-weight: 700;
    letter-spacing: 0.656px;
}

.quickstart-section ol, .block-howto ol {
    margin: 0;
    padding-left: 1.25rem;
    font-size: 12.5px;
    line-height: 1.6;
    font-weight: 400;
}

.quickstart-section ol li, .block-howto ol li {
    margin-bottom: 2px;
}

/* 关于 Demo */
.block-demo {
    width: 100%;
    max-width: 359px;
    align-self: center;
    background: var(--color-surface);
    border-left: 3px solid #888888;
    border-radius: 6px;
    padding: 9.6px 8px 11.2px 11px;
    display: flex;
    flex-direction: column;
    gap: 3.735px;
}

.block-demo p {
    margin: 0;
    font-size: 12.5px;
    color: var(--color-muted);
    line-height: 1.6;
}

.footer-section, .page-footer {
    width: 100%;
    max-width: 359px;
    align-self: center;
    border-top: 1px solid var(--color-border);
    padding-top: 7.4px;
    text-align: center;
}

.footer-section p, .page-footer p {
    margin: 0;
    font-size: 9.6px;
    color: var(--color-footer-text);
    letter-spacing: 0.48px;
}

/* 问答页 */
.chat-subtitle, .kb-subtitle {
    margin: 0;
    text-align: center;
    font-size: 13.1px;
    font-weight: 400;
    color: #888888;
    padding: 1px 0 2px 0;
}

.panel-chat-scroll {
    flex: 1 1 auto;
    min-height: 0;
    overflow-x: hidden;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
    padding-bottom: 12px;
}

.chatbot-container, .chat-board {
    background: var(--color-surface);
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    padding: 16px 10px 20px 10px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    min-height: auto;
    flex-shrink: 0;
}

/* Chatbot bubbles */
.bubble-ai, .message[data-type="bot"] {
    align-self: flex-start;
    max-width: 92%;
    background: #f5f5f5;
    border-radius: 12px 12px 12px 2px;
    padding: 10px 13px 12px 13px;
}

.bubble-ai p, .message[data-type="bot"] p {
    margin: 0;
    font-size: 13.6px;
    line-height: 23.12px;
    color: var(--color-primary);
}

.bubble-ai p + p, .message[data-type="bot"] p + p {
    margin-top: 2px;
}

.bubble-ai strong, .message[data-type="bot"] strong {
    font-weight: 700;
}

.bubble-ai .cite-line {
    margin: 10px 0 0 0;
    font-size: 11.5px;
    line-height: 19.58px;
    color: #888888;
}

.bubble-ai .ref-block {
    margin-top: 12px;
    padding-left: 8px;
    border-left: 2px solid var(--color-accent);
    font-size: 11.5px;
    line-height: 19.58px;
    color: var(--color-muted);
}

.bubble-ai .ref-block p {
    margin: 0;
}

.bubble-ai .ref-block p + p {
    margin-top: 4px;
}

.bubble-ai .ref-block strong {
    font-weight: 700;
    color: var(--color-muted);
}

.bubble-user, .message[data-type="user"] {
    align-self: flex-end;
    max-width: 88%;
    background: var(--color-primary);
    color: #ffffff;
    border-radius: 12px 12px 2px 12px;
    padding: 8px 13px;
    font-size: 13.6px;
    line-height: 21.76px;
}

.input-row {
    margin-top: 0.8rem !important;
    display: flex;
    flex-direction: row;
    gap: 6.39px;
    padding-top: 2px;
}

.input-row textarea, .chat-input {
    width: 100%;
    min-height: 44px;
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    padding: 10px 12px;
    font-family: var(--font-serif);
    font-size: 14px;
    color: var(--color-primary);
    resize: vertical;
    background: #fff !important;
}

.input-row textarea::placeholder, .chat-input::placeholder {
    color: #aaaaaa;
}

.input-row button, .chat-submit {
    width: 100%;
    border: 0;
    border-radius: 10px;
    background: var(--color-primary);
    color: #fff;
    padding: 14px 16px;
    min-height: 52px;
    font-family: var(--font-ui);
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 0.22em;
    cursor: pointer;
}

.input-row button:active, .chat-submit:active {
    opacity: 0.92;
}

.action-row {
    margin-top: 0.5rem !important;
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 6.39px;
    width: 100%;
    padding-top: 4px;
}

.action-row button, .btn-ghost {
    border: 1px solid #d0d0d0;
    border-radius: 9px;
    background: #fff;
    color: var(--color-muted);
    padding: 14px 24px;
    min-height: 50px;
    font-family: var(--font-ui);
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
}

.btn-ghost-dark {
    border: 1px solid var(--color-primary);
    border-radius: 9px;
    background: #fff;
    color: var(--color-primary);
    padding: 14px 24px;
    min-height: 50px;
    font-family: var(--font-ui);
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
}

.examples-section {
    background: #f9f9f9;
    border-radius: 6px;
    padding: 10px 8px 12px 8px;
}

.examples-section label, .examples-label {
    margin: 0 0 6px 0;
    font-size: 11.5px;
    color: #999999;
}

.example-chip {
    display: block;
    width: 100%;
    margin: 0;
    padding: 8px 0;
    border: 0;
    background: transparent;
    text-align: left;
    font-family: var(--font-serif);
    font-size: 12px;
    color: #555555;
    cursor: pointer;
    line-height: 1.45;
}

.example-chip:hover {
    color: var(--color-primary);
}

/* Gradio Examples actual DOM hooks */
.examples-section .label-wrap,
.examples-section .label-wrap label,
.examples-section .examples-label {
    font-size: 11.5px !important;
    color: #999999 !important;
}

.examples-section .examples-table,
.examples-section .examples-row,
.examples-section .examples {
    width: 100% !important;
}

.examples-section .examples-row > button,
.examples-section .examples-table button,
.examples-section .examples button {
    display: block !important;
    width: 100% !important;
    margin: 0 !important;
    padding: 8px 0 !important;
    border: 0 !important;
    background: transparent !important;
    text-align: left !important;
    font-family: var(--font-serif) !important;
    font-size: 12px !important;
    color: #555555 !important;
    line-height: 1.45 !important;
}

.examples-section .examples-row > button:hover,
.examples-section .examples-table button:hover,
.examples-section .examples button:hover {
    color: var(--color-primary) !important;
}

.entity-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    background: #fafafa;
    border: 1px solid var(--color-border);
    border-radius: 6px;
    padding: 12px 11px 12px 11px;
}

.entity-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
}

.entity-card {
    flex: 1 1 calc(50% - 6px);
    min-width: 140px;
    background: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    padding: 8px 10px 10px 10px;
    transition: box-shadow 0.2s;
}

.entity-card:hover {
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.entity-card .entity-name {
    font-size: 12px;
    font-weight: 600;
    color: var(--color-primary);
}

.entity-card .entity-type {
    font-size: 10.9px;
    color: var(--color-accent);
    margin-left: 2px;
}

.entity-card .entity-desc {
    margin: 6px 0 0 0;
    font-size: 10.9px;
    color: var(--color-muted-light);
    line-height: 1.35;
}

.entity-header {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    margin-bottom: 0.3rem;
}

.entity-icon {
    font-size: 1.1rem;
}

.rec-literature {
    background: #fffbf0;
    border: 1px solid #f59e0b;
    border-radius: 6px;
    padding: 10px 9px 10px 9px;
}

.rec-literature h4, .insight-title {
    margin: 0 0 8px 0;
    font-size: 12.5px;
    font-weight: 700;
    color: var(--color-accent);
}

.rec-literature p, .rec-item p {
    margin: 0;
    font-size: 12px;
    color: #555555;
    line-height: 1.75;
}

/* 文献页 */
.panel-docs-scroll {
    flex: 1 1 auto;
    min-height: 0;
    overflow-x: hidden;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
    padding-bottom: 12px;
}

.docs-upload-block {
    background: #fafafa;
    border-left: 3px solid var(--color-accent);
    border-radius: 6px;
    padding: 12px 11px 14px 11px;
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.docs-upload-block h3, .upload-title {
    margin: 0;
    font-size: 13.1px;
    font-weight: 700;
    letter-spacing: 0.656px;
    color: var(--color-primary);
}

.docs-upload-desc, .upload-desc {
    margin: 0;
    font-size: 12.5px;
    line-height: 1.5;
    color: var(--color-muted);
}

.docs-dropzone {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 83px;
    border: 1px dashed #c8c8c8;
    border-radius: 6px;
    background: #ffffff;
    font-size: 12.5px;
    color: var(--color-muted);
    cursor: pointer;
    text-align: center;
    padding: 8px;
}

.docs-dropzone:focus-within {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
}

.docs-file-input {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    opacity: 0;
    cursor: pointer;
    font-size: 0;
}

.docs-actions-col {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.docs-btn-primary {
    width: 100%;
    border: 0;
    border-radius: 6px;
    background: var(--color-primary);
    color: #fff;
    padding: 10px 12px;
    font-family: var(--font-ui);
    font-size: 14px;
    letter-spacing: 0.5px;
    cursor: pointer;
}

.docs-btn-secondary {
    width: 100%;
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    background: #fff;
    color: var(--color-muted);
    padding: 10px 12px;
    font-family: var(--font-ui);
    font-size: 13px;
    cursor: pointer;
}

.docs-upload-status, .upload-status {
    margin: 0;
    padding: 8px 11px;
    border: 1px solid var(--color-border);
    border-radius: 6px;
    background: #fff;
    font-size: 12.5px;
    color: var(--color-muted);
    line-height: 1.45;
}

.kb-stats, .docs-stats {
    display: flex;
    gap: 6px;
    width: 100%;
}

.kb-stat-card, .docs-stat-card {
    flex: 1;
    min-width: 0;
    border: 1px solid var(--color-border);
    border-radius: 6px;
    background: #fff;
    padding: 6px 9px 8px 9px;
}

.kb-stat-card .label, .docs-stat-card .label {
    margin: 0;
    font-size: 11.5px;
    color: var(--color-muted);
}

.kb-stat-card .stat-value, .docs-stat-card .value {
    margin: 4px 0 0 0;
    font-size: 15px;
    font-weight: 700;
    color: var(--color-primary);
    font-family: var(--font-ui);
}

.kb-search-box {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.kb-search-box textarea, .docs-search-input {
    width: 100%;
    min-height: 44px;
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    padding: 10px 12px;
    font-family: var(--font-serif);
    font-size: 13.6px;
    color: var(--color-primary);
}

.kb-search-box textarea::placeholder, .docs-search-input::placeholder {
    color: #aaaaaa;
}

.docs-btn-search {
    width: 100%;
    border: 0;
    border-radius: 6px;
    background: var(--color-primary);
    color: #fff;
    padding: 10px 12px;
    font-family: var(--font-ui);
    font-size: 13px;
    letter-spacing: 2px;
    cursor: pointer;
}

.doc-table-section, .docs-table-wrap {
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    overflow: hidden;
    background: #fff;
}

.docs-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    color: var(--color-primary);
}

.docs-table thead th {
    text-align: left;
    font-weight: 700;
    font-size: 11.5px;
    padding: 8px 7px;
    border-bottom: 1px solid #e8e8e8;
    background: #fafafa;
    white-space: nowrap;
}

.docs-table tbody td {
    padding: 8px 7px;
    border-bottom: 1px solid #f0f0f0;
    vertical-align: top;
}

.docs-table tbody tr:last-child td {
    border-bottom: none;
}

.docs-table .col-num {
    width: 44px;
    text-align: center;
}

/* 底部导航 */
.bottom-nav {
    position: fixed;
    left: 50%;
    transform: translateX(-50%);
    bottom: 0;
    width: 100%;
    max-width: var(--frame-max-width);
    height: var(--bottom-nav-height);
    background: #fff;
    border-top: 1px solid #e5e5e5;
    box-shadow: 0 -2px 10px rgba(0,0,0,0.06);
    display: flex;
    align-items: stretch;
    justify-content: center;
    padding-top: 1px;
    z-index: 20;
}

.bottom-nav button {
    flex: 1;
    min-width: 0;
    border: 0;
    background: transparent;
    padding: 6px 0 8px 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    cursor: pointer;
    font-family: var(--font-ui);
    -webkit-tap-highlight-color: transparent;
}

.bottom-nav button:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
}

.bottom-nav .nav-icon {
    width: 22px;
    height: 22px;
    display: block;
    object-fit: contain;
}

.bottom-nav .nav-label {
    font-size: 10.4px;
    letter-spacing: 0.208px;
    color: var(--color-tab-inactive);
}

.bottom-nav button.is-active .nav-label {
    color: var(--color-accent);
}

/* 文献为选中态时：图标资源为灰阶，用滤镜对齐主题橙 */
.bottom-nav button[data-target="panelDocs"].is-active .nav-icon {
    filter: brightness(0) saturate(100%) invert(52%) sepia(90%) saturate(1600%) hue-rotate(353deg) brightness(96%) contrast(90%);
}

.bottom-nav button[data-target="panelDocs"]:not(.is-active) .nav-icon {
    filter: none;
}

.visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0,0,0,0);
    white-space: nowrap;
    border: 0;
}

/* Mobile bottom tab bar (mini-program style) */
@media (max-width: 768px) {
    html, body { overflow-x: hidden !important; }
    .gradio-container, .main, .gr-app, .app-container {
        padding: 0 8px calc(var(--bottom-nav-height) + 16px) 8px !important;
    }

    .tab-wrapper {
        position: fixed !important;
        bottom: 0 !important;
        left: 0 !important;
        right: 0 !important;
        top: auto !important;
        z-index: 1000 !important;
        display: flex !important;
        flex-direction: row !important;
        justify-content: space-around !important;
        align-items: stretch !important;
        width: 100% !important;
        height: 60px !important;
        min-height: 60px !important;
        margin: 0 !important;
        padding: 0 !important;
        border: none !important;
        border-top: 1px solid #e5e5e5 !important;
        background: #fff !important;
        box-shadow: 0 -2px 10px rgba(0,0,0,0.06) !important;
        overflow: visible !important;
    }

    .tab-wrapper > .tab-container {
        display: flex !important;
        flex-direction: row !important;
        justify-content: space-around !important;
        align-items: center !important;
        width: 100% !important;
        height: 100% !important;
        min-height: 100% !important;
        padding: 0 !important;
        margin: 0 !important;
        border: none !important;
        background: transparent !important;
        pointer-events: auto !important;
    }

    .tab-wrapper > .overflow-menu { display: none !important; }
    .tab-wrapper > .tab-container.visually-hidden { display: none !important; }

    .tab-wrapper button {
        flex: 1 !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 3px !important;
        padding: 6px 0 8px 0 !important;
        margin: 0 !important;
        border: none !important;
        border-bottom: none !important;
        background: none !important;
        font-size: 0.46rem !important;
        font-weight: 500 !important;
        color: #999 !important;
        letter-spacing: 0.02em !important;
        min-width: 0 !important;
        min-height: 0 !important;
        height: auto !important;
        line-height: 1.15 !important;
        border-radius: 0 !important;
        transition: color 0.2s !important;
    }

    .tab-wrapper button::before { content: none !important; }

    .tab-wrapper button.selected {
        color: #E8732A !important;
        background-color: transparent !important;
        border-bottom: none !important;
        font-weight: 600 !important;
    }

    .tabs {
        padding-bottom: 80px !important;
    }
    .tab-wrapper { margin-bottom: 0 !important; }

    /* Mobile-only custom recommended questions */
    .mobile-rec-wrap { display: block !important; }
    .mobile-rec-title {
        font-size: 12px !important;
        color: #999 !important;
        margin: 4px 0 2px 0 !important;
    }
    .mobile-rec-btn {
        width: 100% !important;
        justify-content: flex-start !important;
        text-align: left !important;
        white-space: normal !important;
        line-height: 1.45 !important;
        font-size: 12px !important;
        color: #555 !important;
        background: transparent !important;
        border: none !important;
        padding: 8px 0 !important;
        min-height: unset !important;
        box-shadow: none !important;
    }
    .mobile-rec-btn:hover {
        color: var(--color-primary) !important;
        background: transparent !important;
    }

    /* Slightly lighter gray background for mobile recommendation buttons */
    #rec-btn-1 button,
    #rec-btn-2 button,
    #rec-btn-3 button,
    #rec-btn-4 button,
    #rec-btn-5 button {
        background: #f7f8fa !important;
    }
    /* Hide built-in Gradio Examples on mobile */
    .panel-chat-scroll .examples_wrap,
    .panel-chat-scroll .examples,
    .panel-chat-scroll .gradio-examples {
        display: none !important;
    }
}

/* Desktop adjustments */
@media (min-width: 769px) {
    .gradio-container, .main, .gr-app, .app-container {
        padding: 0 1.5rem 1.5rem 1.5rem !important;
        max-width: 1200px;
    }

    .content-inner {
        max-width: 1200px;
        margin: 0 auto;
        width: 100%;
    }

    .top-header h1 {
        font-size: 3.4rem !important;
    }

    .top-header .tagline {
        font-size: 1rem !important;
    }

    .feature-grid {
        gap: 1.2rem !important;
        margin: 1.8rem 0 !important;
    }

    .feature-card {
        padding: 1.6rem 1.2rem !important;
        min-height: 150px !important;
    }

    .feature-card h3 {
        font-size: 1.4rem !important;
        margin-bottom: 0.6rem !important;
    }

    .feature-card p {
        font-size: 0.95rem !important;
        line-height: 1.65 !important;
    }

    .tabs { border: none !important; }
    .tabs > .tab-wrapper {
        border-bottom: 2px solid #E8E8E8 !important;
        margin-bottom: 1.2rem !important;
        position: relative !important;
        bottom: auto !important;
        left: auto !important;
        right: auto !important;
        transform: none !important;
        box-shadow: none !important;
    }
    .tabs > .tab-wrapper > .tab-container[role="tablist"] > button[role="tab"] {
        font-size: 1.25rem !important;
        font-weight: 500 !important;
        color: #666 !important;
        letter-spacing: 0.05em !important;
        padding: 0.7rem 1.5rem !important;
    }
    .tabs > .tab-wrapper > .tab-container[role="tablist"] > button[role="tab"].selected {
        color: #1a1a2e !important;
        border-bottom: 2px solid #1a1a2e !important;
        font-weight: 600 !important;
    }

    .input-row { flex-direction: row !important; }

    /* Desktop-only bottom information blocks */
    .quickstart-section,
    .quickstart-section.demo-section,
    .footer-section,
    .page-footer {
        max-width: none !important;
        width: 100% !important;
        align-self: stretch !important;
    }

    /* Desktop search box adjustments */
    .kb-search-box {
        flex-direction: row !important;
        gap: 12px !important;
        max-width: 800px !important;
        margin: 0 auto !important;
    }

    .kb-search-box textarea,
    .docs-search-input {
        min-height: 56px !important;
        font-size: 1.1rem !important;
        padding: 12px 16px !important;
    }

    .quickstart-section {
        padding: 1.75rem 2rem !important;
    }

    .quickstart-section h3 {
        font-size: 1.4rem !important;
    }

    .quickstart-section ol,
    .quickstart-section.demo-section p,
    .footer-section p,
    .page-footer p {
        font-size: 1rem !important;
        line-height: 1.85 !important;
    }

    .quickstart-section.demo-section p {
        margin: 0;
    }

    .footer-section,
    .page-footer {
        padding-top: 12px !important;
        text-align: center !important;
    }
}
"""


# 与 Figma 设计稿一致：标题衬线体（Noto Serif SC）
FIGMA_HEAD_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com"/>'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>'
    '<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700&display=swap" rel="stylesheet"/>'
)


TAB_ICON_JS = """
<script>
(function(){
    // Force light theme ONLY on mobile - do NOT affect desktop
    if (window.innerWidth >= 768) return;
    document.documentElement.style.colorScheme = 'light';
    document.documentElement.setAttribute('data-theme', 'light');
    document.documentElement.classList.remove('dark');
    document.body && document.body.classList.remove('dark');
    var s = document.createElement('style');
    s.id = 'force-light-mobile';
    s.textContent = '*, *::before, *::after { color-scheme: light !important; }'
        + 'html.dark, html[data-theme="dark"] { --bg-primary: #ffffff !important; --bg-secondary: #f7f7f8 !important; --bg-tertiary: #f0f0f1 !important; --body-text-fill: #1a1a1a !important; --background-fill-primary: #ffffff !important; --background-fill-secondary: #f7f7f8 !important; --background-fill-tertiary: #f0f0f1 !important; --border-color-primary: #e5e7eb !important; --border-color-secondary: #d1d5db !important; --neutral-50: #f9fafb !important; --neutral-100: #f3f4f6 !important; --neutral-200: #e5e7eb !important; --neutral-300: #d1d5db !important; --neutral-400: #9ca3af !important; --neutral-500: #6b7280 !important; --neutral-600: #4b5563 !important; --neutral-700: #374151 !important; --neutral-800: #1f2937 !important; --neutral-900: #111827 !important; --color-accent: #E8732A !important; --color-accent-soft: #fde6d5 !important; --text-primary: #1a1a1a !important; --text-secondary: #4b5563 !important; --text-tertiary: #6b7280 !important; }'
        + 'html, body, .gradio-container, .main, .gr-app, .app-container, .tabs, .tabitem, [class*="tab"] { background-color: #ffffff !important; background: #ffffff !important; color: #1a1a1a !important; }'
        + '.chatbot-container, .chatbot-container *, .prose, .prose *, .message, .message * { background-color: #ffffff !important; background: #ffffff !important; color: #1a1a1a !important; }'
        + '.tab-wrapper, .tab-wrapper button, .tab-wrapper * { background: #ffffff !important; background-color: #ffffff !important; }'
        + 'table, table td, table th, table tr, table * { color: #000000 !important; background: #ffffff !important; }'
        + '.doc-table-section, .doc-table-section *, .upload-section, .upload-section * { color: #000000 !important; background: #ffffff !important; }';
    document.head.appendChild(s);
    var mo = new MutationObserver(function(mutations){
        mutations.forEach(function(m){
            if(m.attributeName === 'class'){
                document.documentElement.classList.remove('dark');
                if(document.body) document.body.classList.remove('dark');
            }
        });
    });
    mo.observe(document.documentElement, {attributes: true});
    if(document.body) mo.observe(document.body, {attributes: true});
})();
(function(){
    // 首页态底部栏图标（Figma 首页 Frame）
    const navIconUrlsHomeActive = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" width="22" height="22"><path d="M18.75 8.75V18.75H13.25V14.25C13.25 12.317 11.683 10.75 9.75 10.75C7.817 10.75 6.25 12.317 6.25 14.25V18.75H0.75V8.75L9.75 0.75L18.75 8.75Z" fill="currentColor"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 19" width="22" height="22"><path d="M8.90527 0C13.8237 0 17.8115 3.57438 17.8115 7.9834C17.8115 10.2018 16.8005 12.2075 15.1709 13.6543L16.0635 18.4805L11.9844 15.4756C11.0248 15.7925 9.98758 15.9668 8.90527 15.9668C3.98706 15.9666 9.68785e-05 12.3923 0 7.9834C0 3.57447 3.987 0.000151543 8.90527 0Z" fill="currentColor"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 19 20" width="22" height="22"><path d="M13 0C16.3137 0 19 2.68629 19 6V14C19 17.3137 16.3137 20 13 20H6C2.68629 20 1.28855e-07 17.3137 0 14V6C1.28855e-07 2.68629 2.68629 0 6 0H13ZM3.5 8.75C3.08579 8.75 2.75 9.08579 2.75 9.5C2.75 9.91421 3.08579 10.25 3.5 10.25H10.5C10.9142 10.25 11.25 9.91421 11.25 9.5C11.25 9.08579 10.9142 8.75 10.5 8.75H3.5ZM3.5 4.75C3.08579 4.75 2.75 5.08579 2.75 5.5C2.75 5.91421 3.08579 6.25 3.5 6.25H14.5C14.9142 6.25 15.25 5.91421 15.25 5.5C15.25 5.08579 14.9142 4.75 14.5 4.75H3.5Z" fill="currentColor"/></svg>'
    ];
    // 问答态底部栏图标（Figma 问答 Frame 1:134）
    const navIconUrlsChatActive = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" width="22" height="22"><path d="M18.75 8.75V18.75H13.25V14.25C13.25 12.317 11.683 10.75 9.75 10.75C7.817 10.75 6.25 12.317 6.25 14.25V18.75H0.75V8.75L9.75 0.75L18.75 8.75Z" fill="currentColor"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 19" width="22" height="22"><path d="M8.90527 0C13.8237 0 17.8115 3.57438 17.8115 7.9834C17.8115 10.2018 16.8005 12.2075 15.1709 13.6543L16.0635 18.4805L11.9844 15.4756C11.0248 15.7925 9.98758 15.9668 8.90527 15.9668C3.98706 15.9666 9.68785e-05 12.3923 0 7.9834C0 3.57447 3.987 0.000151543 8.90527 0Z" fill="currentColor"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 19 20" width="22" height="22"><path d="M13 0C16.3137 0 19 2.68629 19 6V14C19 17.3137 16.3137 20 13 20H6C2.68629 20 1.28855e-07 17.3137 0 14V6C1.28855e-07 2.68629 2.68629 0 6 0H13ZM3.5 8.75C3.08579 8.75 2.75 9.08579 2.75 9.5C2.75 9.91421 3.08579 10.25 3.5 10.25H10.5C10.9142 10.25 11.25 9.91421 11.25 9.5C11.25 9.08579 10.9142 8.75 10.5 8.75H3.5ZM3.5 4.75C3.08579 4.75 2.75 5.08579 2.75 5.5C2.75 5.91421 3.08579 6.25 3.5 6.25H14.5C14.9142 6.25 15.25 5.91421 15.25 5.5C15.25 5.08579 14.9142 4.75 14.5 4.75H3.5Z" fill="currentColor"/></svg>'
    ];
    // 文献态：首页与问答为灰态图标，文献为灰图标（高亮由 Tab 文字颜色表示；与问答页同源资源）
    const navIconUrlsDocsActive = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" width="22" height="22"><path d="M18.75 8.75V18.75H13.25V14.25C13.25 12.317 11.683 10.75 9.75 10.75C7.817 10.75 6.25 12.317 6.25 14.25V18.75H0.75V8.75L9.75 0.75L18.75 8.75Z" fill="currentColor"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 19" width="22" height="22"><path d="M8.90527 0C13.8237 0 17.8115 3.57438 17.8115 7.9834C17.8115 10.2018 16.8005 12.2075 15.1709 13.6543L16.0635 18.4805L11.9844 15.4756C11.0248 15.7925 9.98758 15.9668 8.90527 15.9668C3.98706 15.9666 9.68785e-05 12.3923 0 7.9834C0 3.57447 3.987 0.000151543 8.90527 0Z" fill="currentColor"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 19 20" width="22" height="22"><path d="M13 0C16.3137 0 19 2.68629 19 6V14C19 17.3137 16.3137 20 13 20H6C2.68629 20 1.28855e-07 17.3137 0 14V6C1.28855e-07 2.68629 2.68629 0 6 0H13ZM3.5 8.75C3.08579 8.75 2.75 9.08579 2.75 9.5C2.75 9.91421 3.08579 10.25 3.5 10.25H10.5C10.9142 10.25 11.25 9.91421 11.25 9.5C11.25 9.08579 10.9142 8.75 10.5 8.75H3.5ZM3.5 4.75C3.08579 4.75 2.75 5.08579 2.75 5.5C2.75 5.91421 3.08579 6.25 3.5 6.25H14.5C14.9142 6.25 15.25 5.91421 15.25 5.5C15.25 5.08579 14.9142 4.75 14.5 4.75H3.5Z" fill="currentColor"/></svg>'
    ];

    const navIconElements = [];

    function applyNavIcons(activePanelId){
        let iconSet = navIconUrlsHomeActive;
        if(activePanelId === 'panelChat') iconSet = navIconUrlsChatActive;
        else if(activePanelId === 'panelDocs') iconSet = navIconUrlsDocsActive;

        navIconElements.forEach(function(span, index){
            if(span && iconSet[index]){
                span.innerHTML = iconSet[index];
            }
        });
    }

    // Only run on mobile (match @media (max-width: 768px) in CSS)
    if (window.innerWidth < 768) {
        var _injected = false;
        var _mutating = false;

        // Push tab bar up to clear system nav bar (Android/iOS)
        function applySafeArea(){
            var wrapper = document.querySelector('.tab-wrapper');
            if(!wrapper) return;
            var extra = 0;
            if(window.visualViewport && window.visualViewport.height < window.innerHeight){
                extra = window.innerHeight - window.visualViewport.height;
            }
            if(extra < 12) extra = 12;
            wrapper.style.height = 'calc(60px + ' + extra + 'px)';
            wrapper.style.paddingBottom = extra + 'px';
            var tabs = document.querySelector('.tabs');
            if(tabs) tabs.style.paddingBottom = 'calc(80px + ' + extra + 'px)';
        }

        function injectIcons(){
            if(_injected) return true;
            var wrapper = document.querySelector('.tab-wrapper');
            if(!wrapper) return false;

            var allBtns = wrapper.querySelectorAll('button');
            var visibleBtns = [];
            allBtns.forEach(function(btn){
                var rect = btn.getBoundingClientRect();
                if(rect.width > 0 && rect.height > 0 && getComputedStyle(btn).display !== 'none'){
                    visibleBtns.push(btn);
                }
            });
            if(visibleBtns.length < 3) return false;

            var btns = visibleBtns.slice(0,3);

            _mutating = true;
            btns.forEach(function(btn, i){
                var existing = btn.querySelector('.tab-icon-svg');
                if(existing) { navIconElements.push(existing); return; }
                btn.style.setProperty('flex-direction','column','important');
                btn.style.setProperty('align-items','center','important');
                btn.style.setProperty('justify-content','center','important');
                btn.style.setProperty('padding-top','6px','important');
                var span = document.createElement('span');
                span.className = 'tab-icon-svg';
                span.style.cssText = 'display:block;line-height:1;margin-bottom:4px;pointer-events:none;color:inherit;';
                span.innerHTML = navIconUrlsHomeActive[i];
                navIconElements.push(span);
                btn.insertBefore(span, btn.firstChild);
            });
            _mutating = false;
            _injected = true;
            applySafeArea();
            return true;
        }

        var observer = new MutationObserver(function(){
            if(_mutating) return;
            if(!_injected){ injectIcons(); }
        });
        observer.observe(document.body, {childList:true, subtree:true, attributes:true, attributeFilter:['class','aria-selected']});

        function tryInject(){
            injectIcons();
            if(!_injected) setTimeout(tryInject, 800);
        }

        if(document.readyState === 'loading'){
            document.addEventListener('DOMContentLoaded', tryInject);
        } else {
            tryInject();
        }

        if(window.visualViewport){
            window.visualViewport.addEventListener('resize', function(){
                if(_injected) applySafeArea();
            });
        }

        window.addEventListener('resize', function(){
            if(window.innerWidth >= 768 && _injected){
                var wrapper = document.querySelector('.tab-wrapper');
                if(wrapper){
                    var containers = wrapper.querySelectorAll('.tab-container');
                    containers.forEach(function(c){
                        if(!c.classList.contains('visually-hidden')){
                            c.querySelectorAll('button .tab-icon-svg').forEach(function(el){ el.remove(); });
                        }
                    });
                    wrapper.style.paddingBottom = '';
                }
                var tabs = document.querySelector('.tabs');
                if(tabs) tabs.style.paddingBottom = '';
                _injected = false;
            } else if(window.innerWidth < 768 && !_injected){
                tryInject();
            }
        });
    }
})();
</script>
"""


# ===================== 回调函数 =====================

def respond(message, history):
    """处理一轮问答：检索 → LLM 生成 → 实体/推荐 → 返回。"""
    history = history or []

    message = (message or "").strip()
    if not message:
        return history, "", "", ""

    try:
        chunks = retrieve(message, top_k=5) or []

        answer = ask_llm(message, chunks, chat_history=history)
        answer = answer if isinstance(answer, str) else str(answer)

        # 去重：移除 LLM 自行生成的参考来源段落
        answer = clean_answer(answer)

        # 追加系统生成的参考来源
        answer = append_sources(answer, chunks)

        # Gradio 6.x Chatbot messages format
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": answer})

        # 生成文献推荐
        rec_html = ""
        try:
            rec_html = recommend_docs(message, chunks)
        except Exception:
            rec_html = ""

        return history, "", rec_html, ""
    except Exception as e:
        err_text = f"系统处理该问题时出现异常：{str(e)}"
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": err_text})
        return history, "", "", ""


def export_chat(history):
    """导出对话记录为 Markdown 文件，返回绝对路径供下载。"""
    if not history:
        return None

    lines = []
    lines.append("# 知域 · 问答记录\n\n")
    lines.append(f"> 导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    lines.append("---\n\n")

    for turn in history:
        if isinstance(turn, (list, tuple)) and len(turn) == 2:
            user_msg, assistant_msg = turn
            if user_msg:
                lines.append(f"### 🙋 提问\n\n{user_msg}\n\n")
            if assistant_msg:
                lines.append(f"### 📖 回答\n\n{assistant_msg}\n\n")
        elif isinstance(turn, dict):
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "user":
                lines.append(f"### 🙋 提问\n\n{content}\n\n")
            elif role == "assistant":
                lines.append(f"### 📖 回答\n\n{content}\n\n")
        lines.append("---\n\n")

    md_content = "".join(lines)

    fd, export_path = tempfile.mkstemp(suffix=".md", prefix="zhiyu_export_", text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(md_content)
    return os.path.abspath(export_path)


def clear_chat():
    """清空对话历史和洞察面板。"""
    return [], "", ""


# ===================== Gradio 界面 =====================

def build_demo():
    """构建并返回 Gradio Blocks 应用实例。"""

    with gr.Blocks(
        title="知域 - 深圳近现代建筑遗产知识助手",
    ) as demo:

        gr.HTML("""
        <div class="top-header">
            <h1>知域</h1>
            <p class="tagline">ZHIYU · AI 学术文献助手</p>
        </div>
        """)

        with gr.Tabs(selected="tab_home") as tabs:

            # ========== Tab 1: 首页 ==========
            with gr.Tab("首页", id="tab_home"):

                go_chat_btn = gr.Button("快速开始问答 →", elem_id="go-chat-btn")

                gr.HTML("""
                <div class="content-inner">
                <div class="hero-section">
                    <h2>让每个学术团队拥有自己的 AI 文献助手</h2>
                    <p class="hero-desc">
                        <span class="demo-badge">Demo 领域：深圳近现代建筑遗产</span>
                    </p>
                </div>
                <div class="feature-grid">
                    <div class="feature-card">
                        <h3>上传文献</h3>
                        <p>支持 PDF、Word 等格式<br>自动解析、分块、向量化</p>
                    </div>
                    <div class="feature-card">
                        <h3>智能问答</h3>
                        <p>基于 RAG 检索增强生成<br>回答专业、有据可查</p>
                    </div>
                    <div class="feature-card">
                        <h3>溯源引用</h3>
                        <p>每条回答标注来源文献<br>支持一键定位原文片段</p>
                    </div>
                    <div class="feature-card">
                        <h3>实体识别</h3>
                        <p>自动提取建筑、人物等实体<br>生成结构化知识卡片</p>
                    </div>
                    <div class="feature-card">
                        <h3>文献推荐</h3>
                        <p>基于问答内容智能推荐<br>发现更多相关文献</p>
                    </div>
                    <div class="feature-card">
                        <h3>多领域接入</h3>
                        <p>不限于建筑遗产<br>任意学科文献均可搭建</p>
                    </div>
                </div>
                <div class="quickstart-section">
                    <h3>如何使用</h3>
                    <ol>
                        <li>切换到「问答」页签，输入您的研究问题</li>
                        <li>AI 将从知识库中检索相关文献片段并生成专业回答</li>
                        <li>每条回答底部标注参考来源，确保信息可追溯</li>
                        <li>切换到「文献」查看当前知识库收录的文献列表</li>
                    </ol>
                </div>
                <div class="quickstart-section demo-section">
                    <h3>关于本 Demo</h3>
                    <p>
                        当前展示的是「深圳近现代建筑遗产」领域的模板效果。<br>
                        知识库已收录 30+ 篇学术文献，涵盖深圳改革开放以来的建筑发展历程。<br>
                        「知域」支持任意学科文献接入，可快速搭建专属知识 Agent。
                    </p>
                </div>
                <div class="footer-section">
                    <p>知域 &copy; 2026 &middot; 腾讯PCG校园AI产品创意大赛参赛作品</p>
                </div>
                </div>
                """)

                go_chat_btn.click(fn=lambda: gr.Tabs(selected="tab_chat"), outputs=tabs)

            # ========== Tab 2: 问答 ==========
            with gr.Tab("问答", id="tab_chat"):
                with gr.Column():
                    gr.HTML("""
                    <p class="chat-subtitle">基于知识库的智能问答 · 所有回答均标注参考来源</p>
                    """)

                    chatbot = gr.Chatbot(
                        label="",
                        height=400,
                    )

                    with gr.Row():
                        msg_input = gr.Textbox(
                            placeholder="请输入您的问题，如：深圳国贸大厦的施工技术创新有哪些？",
                            show_label=False,
                            scale=9,
                            lines=1,
                        )
                        send_btn = gr.Button("提 问", scale=1, variant="primary")

                    with gr.Row():
                        clear_btn = gr.Button("清空对话", scale=1)
                        export_btn = gr.Button("导出对话", scale=1, variant="secondary")
                        export_file = gr.File(label="对话导出（点击下载）", visible=True)

                    rec_questions = [
                        "深圳国贸大厦在建设中有哪些技术突破？",
                        "早期深圳的高层酒店建筑有什么共同的设计特点？",
                        "'当代遗产'概念在深圳建筑语境下是如何被讨论的？",
                        "蛇口工业区早期建筑群有什么遗产价值？",
                        "深圳白沙岭高层住宅区的设计有什么特色？",
                    ]

                    with gr.Column():
                        gr.HTML('<p class="mobile-rec-title">推荐问题</p>')
                        rec_btn_1 = gr.Button(rec_questions[0], variant="secondary", elem_id="rec-btn-1")
                        rec_btn_2 = gr.Button(rec_questions[1], variant="secondary", elem_id="rec-btn-2")
                        rec_btn_3 = gr.Button(rec_questions[2], variant="secondary", elem_id="rec-btn-3")
                        rec_btn_4 = gr.Button(rec_questions[3], variant="secondary", elem_id="rec-btn-4")
                        rec_btn_5 = gr.Button(rec_questions[4], variant="secondary", elem_id="rec-btn-5")

                    entity_output = gr.HTML(value="")
                    rec_output = gr.HTML(value="")

                    gr.HTML("""
                    <div class="footer-section">
                        <p>知域 &copy; 2026 &middot; 当前展示建筑遗产领域模板 &middot; 支持任意学科文献接入</p>
                    </div>
                    """)

                msg_input.submit(respond, [msg_input, chatbot], [chatbot, entity_output, rec_output, msg_input])
                send_btn.click(respond, [msg_input, chatbot], [chatbot, entity_output, rec_output, msg_input])

                rec_btn_1.click(lambda: rec_questions[0], outputs=msg_input)
                rec_btn_2.click(lambda: rec_questions[1], outputs=msg_input)
                rec_btn_3.click(lambda: rec_questions[2], outputs=msg_input)
                rec_btn_4.click(lambda: rec_questions[3], outputs=msg_input)
                rec_btn_5.click(lambda: rec_questions[4], outputs=msg_input)

                clear_btn.click(
                    fn=clear_chat,
                    outputs=[chatbot, entity_output, rec_output]
                )
                export_btn.click(
                    fn=export_chat,
                    inputs=[chatbot],
                    outputs=[export_file]
                )

            # ========== Tab 3: 文献管理 ==========
            with gr.Tab("文献", id="tab_kb"):
                with gr.Column():
                    gr.HTML("""
                    <p class="kb-subtitle">浏览知识库收录的文献 · 上传新文献 · 搜索文献内容</p>
                    """)

                    gr.HTML("""
                    <div class="upload-section docs-upload-figma">
                        <h3 class="upload-title">上传文献</h3>
                        <p class="upload-desc">支持 PDF、TXT、Markdown 格式，文件将自动解析并分块加入知识库</p>
                    </div>
                    """)

                    with gr.Row():
                        upload_file = gr.File(
                            label="选择文献文件（支持多选）",
                            file_types=[".pdf", ".txt", ".md"],
                            file_count="multiple",
                        )

                    with gr.Row():
                        upload_btn = gr.Button("上传并导入知识库", variant="primary")
                        upload_clear_btn = gr.Button("清空选择")

                    upload_result = gr.Markdown(
                        value="",
                        visible=True,
                    )

                    with gr.Row():
                        doc_count_display = gr.Textbox(
                            label="文献数量",
                            interactive=False,
                            scale=1,
                        )
                        chunk_count_display = gr.Textbox(
                            label="知识片段数",
                            interactive=False,
                            scale=1,
                        )

                    with gr.Row():
                        kb_search_input = gr.Textbox(
                            placeholder="搜索文献内容（输入关键词，如：国贸、蛇口、遗产）",
                            show_label=False,
                            scale=4,
                            lines=1,
                        )
                        kb_search_btn = gr.Button("搜 索", scale=1, variant="secondary")

                    doc_table_output = gr.Markdown(
                        value="加载中...",
                    )

                    gr.HTML("""
                    <div class="footer-section">
                        <p>知域 &copy; 2026 &middot; 知识库数据仅供学术研究使用</p>
                    </div>
                    """)

                # KB events
                demo.load(
                    fn=lambda: (
                        get_kb_stats()[0],   # doc count text
                        get_kb_stats()[1],   # chunk count text
                        build_doc_table()    # doc table
                    ),
                    outputs=[doc_count_display, chunk_count_display, doc_table_output]
                )

                kb_search_btn.click(
                    fn=search_docs,
                    inputs=[kb_search_input],
                    outputs=[doc_table_output]
                )
                kb_search_input.submit(
                    fn=search_docs,
                    inputs=[kb_search_input],
                    outputs=[doc_table_output]
                )

                # Upload events
                upload_file.change(
                    fn=upload_document,
                    inputs=[upload_file],
                    outputs=[upload_result, doc_table_output, doc_count_display, chunk_count_display]
                )
                upload_btn.click(
                    fn=upload_document,
                    inputs=[upload_file],
                    outputs=[upload_result, doc_table_output, doc_count_display, chunk_count_display]
                )
                # Clear button
                def clear_upload():
                    return "", build_doc_table(), get_kb_stats()[0], get_kb_stats()[1]
                upload_clear_btn.click(
                    fn=clear_upload,
                    outputs=[upload_result, doc_table_output, doc_count_display, chunk_count_display]
                )

    return demo
