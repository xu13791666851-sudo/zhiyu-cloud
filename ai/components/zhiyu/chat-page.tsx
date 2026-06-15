"use client"

import { useEffect, useRef, useState } from "react"
import {
  AlertCircle,
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Database,
  Download,
  FileText,
  Layers3,
  ListChecks,
  Send,
  Sparkles,
  Trash2,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"

interface Source {
  id: string
  title: string
  author: string
  year: string
  page: string
  excerpt: string
  credibility: "high" | "medium" | "low"
  type: string
  provider?: string
  embeddingModel?: string
  documentId?: number
  chunkIndex?: number
  embeddingScore?: number
  keywordScore?: number
  rerankScore?: number
  coverageScore?: number
  sectionTitle?: string
}

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  sources?: Source[]
  agent?: AgentTrace
}

interface AgentStep {
  name: string
  tool?: string
  detail: string
  status?: string
}

interface AgentTrace {
  task: string
  task_label: string
  steps: AgentStep[]
  selected_document_ids?: number[]
  selection_reason?: string
  citation_check?: CitationCheck
}

interface CitationCheck {
  evidence_state: string
  available_source_count: number
  cited_source_count: number
  cited_sources: string[]
  unsupported_citations: string[]
}

interface ApiChunk {
  content: string
  doc?: string
  credibility?: "high" | "medium" | "low"
  document_id?: number
  provider?: string | null
  embedding_model?: string | null
  embedding_score?: number | null
  keyword_score?: number | null
  rerank_score?: number | null
  coverage_score?: number | null
  chunk_index?: number | null
  page_start?: number | null
  page_end?: number | null
  source_type?: string | null
  section_title?: string | null
}

interface ApiDocument {
  id: number
  title: string
  file_name: string | null
  status: string
  chunk_count: number
}

interface ChatPageProps {
  selectedDocumentId?: number | null
  onDocumentScopeChange?: (documentId: number | null) => void
  initialQuestion?: string | null
  onInitialQuestionConsumed?: () => void
}

const credibilityConfig = {
  high: {
    label: "High confidence",
    icon: CheckCircle2,
    className: "bg-green-500/10 text-green-400 border-green-500/20",
  },
  medium: {
    label: "Medium confidence",
    icon: AlertTriangle,
    className: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  },
  low: {
    label: "Low confidence",
    icon: AlertCircle,
    className: "bg-red-500/10 text-red-400 border-red-500/20",
  },
}

const initialMessages: Message[] = [
  {
    id: "welcome",
    role: "assistant",
    content:
      "Hi, I am ZhiYu Research Agent. I can summarize one paper, compare papers, search related studies, and draft cited literature reviews from your parsed documents.",
  },
]

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"
const ALL_DOCUMENTS_SCOPE = "all"

function getDocumentDisplayName(document: ApiDocument) {
  return document.title || document.file_name || `Document ${document.id}`
}

function looksMojibake(value?: string | null) {
  const text = (value || "").trim()
  if (!text) return false
  const markerHits = (text.match(/[\u00c0-\u00ff]/g) || []).length
  const cjkHits = (text.match(/[\u4e00-\u9fff]/g) || []).length
  const replacementHits = (text.match(/\ufffd/g) || []).length
  return replacementHits > 0 || (markerHits >= 2 && cjkHits < 4)
}

function cleanCitationText(value?: string | null, fallback?: string) {
  const text = (value || "").trim()
  if (text && !looksMojibake(text)) return text
  if (fallback && !looksMojibake(fallback)) return fallback
  return undefined
}

function formatChunkPage(chunk: ApiChunk) {
  if (!chunk.page_start) return ""
  if (!chunk.page_end || chunk.page_end === chunk.page_start) {
    return `p. ${chunk.page_start}`
  }
  return `pp. ${chunk.page_start}-${chunk.page_end}`
}

function toSource(chunk: ApiChunk, index: number): Source {
  const docTitle =
    cleanCitationText(
      chunk.doc,
      chunk.document_id !== undefined ? `Document ${chunk.document_id}` : "Unknown source",
    ) || "Unknown source"
  const sectionTitle = cleanCitationText(chunk.section_title)
  return {
    id: `src-${index}`,
    title: docTitle,
    author: "",
    year: "",
    page: formatChunkPage(chunk),
    excerpt: chunk.content?.slice(0, 260) || "",
    credibility: chunk.credibility || "medium",
    type: chunk.source_type || "",
    provider: chunk.provider || undefined,
    embeddingModel: chunk.embedding_model || undefined,
    documentId: chunk.document_id,
    chunkIndex: chunk.chunk_index ?? undefined,
    embeddingScore: chunk.embedding_score ?? undefined,
    keywordScore: chunk.keyword_score ?? undefined,
    rerankScore: chunk.rerank_score ?? undefined,
    coverageScore: chunk.coverage_score ?? undefined,
    sectionTitle,
  }
}

function extractApiChunks(data: any): ApiChunk[] {
  const candidates = [
    data?.chunks,
    data?.sources,
    data?.references,
    data?.results,
    data?.retrieval?.chunks,
  ]
  const chunks = candidates.find((item) => Array.isArray(item))
  return chunks || []
}

function formatScore(value?: number) {
  if (typeof value !== "number" || Number.isNaN(value)) return "--"
  return value.toFixed(3)
}

function formatRawScore(value?: number) {
  if (typeof value !== "number" || Number.isNaN(value)) return "--"
  if (value >= 100) return value.toFixed(0)
  return value.toFixed(3)
}

function scorePercent(value?: number) {
  if (typeof value !== "number" || Number.isNaN(value)) return 0
  return Math.max(0, Math.min(100, value * 100))
}

function ScoreBar({ label, value }: { label: string; value?: number }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <span>{label}</span>
        <span className="font-mono text-foreground/80">{formatScore(value)}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-background/70">
        <div
          className="h-full rounded-full bg-primary/80"
          style={{ width: `${scorePercent(value)}%` }}
        />
      </div>
    </div>
  )
}

function AgentTracePanel({ agent }: { agent: AgentTrace }) {
  return (
    <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-medium text-foreground">
          <ListChecks className="h-4 w-4 text-primary" />
          <span>Agent 工作流程</span>
        </div>
        <Badge variant="outline" className="border-primary/20 bg-primary/10 text-primary">
          {agent.task_label || agent.task}
        </Badge>
      </div>
      {agent.citation_check && (
        <div className="mb-2 flex flex-wrap items-center gap-2 rounded-md border border-border/40 bg-background/30 px-2.5 py-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">证据状态：{agent.citation_check.evidence_state}</span>
          <span>已引用 {agent.citation_check.cited_source_count}/{agent.citation_check.available_source_count} 条来源</span>
        </div>
      )}
      <div className="space-y-2">
        {agent.steps.map((step, index) => (
          <div key={`${step.name}-${index}`} className="flex gap-2 text-xs">
            <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border border-primary/30 bg-primary/10 text-[10px] font-semibold text-primary">
              {index + 1}
            </div>
            <div className="min-w-0">
              <div className="font-medium text-foreground">{step.name}</div>
              <div className="leading-relaxed text-muted-foreground">{step.detail}</div>
            </div>
          </div>
        ))}
      </div>
      {agent.selection_reason && (
        <div className="mt-2 rounded-md border border-border/40 bg-background/30 px-2.5 py-2 text-xs leading-relaxed text-muted-foreground">
          {agent.selection_reason}
        </div>
      )}
    </div>
  )
}

function EvidenceCard({
  source,
  isExpanded,
  onToggle,
  index,
}: {
  source: Source
  isExpanded: boolean
  onToggle: () => void
  index: number
}) {
  const config = credibilityConfig[source.credibility]
  const Icon = config.icon

  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border bg-secondary/30 transition-colors",
        isExpanded ? "border-primary/60 bg-primary/5" : "border-border/50 hover:border-primary/30",
      )}
    >
      <button
        onClick={onToggle}
        className="flex w-full items-start justify-between gap-3 p-3 text-left"
      >
        <div className="flex min-w-0 flex-1 gap-2">
          <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-primary/30 bg-primary/10 text-xs font-semibold text-primary">
            {index + 1}
          </div>
          <div className="min-w-0 space-y-1">
            <p className="line-clamp-2 text-sm font-medium leading-snug text-foreground">
              {source.title}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {source.page && (
                <Badge variant="outline" className="h-5 border-border/70 px-1.5 text-[10px] text-muted-foreground">
                  <BookOpen className="mr-1 h-3 w-3" />
                  {source.page}
                </Badge>
              )}
              {source.sectionTitle && (
                <Badge variant="outline" className="h-5 border-border/70 px-1.5 text-[10px] text-muted-foreground">
                  {source.sectionTitle}
                </Badge>
              )}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <Badge variant="outline" className={cn("text-xs", config.className)}>
            <Icon className="mr-1 h-3 w-3" />
            {config.label}
          </Badge>
          {isExpanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </button>
      {isExpanded && (
        <div className="space-y-3 border-t border-border/50 p-3">
          <div className="space-y-1.5">
            <div className="text-[11px] font-medium uppercase text-muted-foreground">
              支持片段
            </div>
            <div className="rounded-md border border-border/40 bg-background/40 p-2.5 text-xs leading-relaxed text-foreground/80">
              "{source.excerpt}"
            </div>
          </div>
          <details className="group rounded-md border border-border/40 bg-background/30">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-2.5 py-2 text-xs text-muted-foreground transition-colors hover:text-foreground">
              <span>检索细节</span>
              <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
            </summary>
            <div className="space-y-3 border-t border-border/40 p-2.5">
              <div className="flex flex-wrap gap-1.5 text-xs text-muted-foreground">
                {source.author && <span>Author: {source.author}</span>}
                {source.documentId !== undefined && (
                  <Badge variant="outline" className="h-5 border-border/70 px-1.5 text-[10px] text-muted-foreground">
                    doc {source.documentId}
                  </Badge>
                )}
                {source.chunkIndex !== undefined && (
                  <Badge variant="outline" className="h-5 border-border/70 px-1.5 text-[10px] text-muted-foreground">
                    <Layers3 className="mr-1 h-3 w-3" />
                    chunk {source.chunkIndex}
                  </Badge>
                )}
                {source.type && (
                  <Badge variant="outline" className="h-5 border-border/70 px-1.5 text-[10px] text-muted-foreground">
                    {source.type}
                  </Badge>
                )}
                {source.provider && (
                  <Badge variant="outline" className="h-5 border-cyan-500/20 bg-cyan-500/10 px-1.5 text-[10px] text-cyan-300">
                    <Database className="mr-1 h-3 w-3" />
                    {source.provider}
                  </Badge>
                )}
                {source.embeddingModel && (
                  <Badge variant="outline" className="h-5 border-primary/20 bg-primary/10 px-1.5 text-[10px] text-primary">
                    <Sparkles className="mr-1 h-3 w-3" />
                    {source.embeddingModel}
                  </Badge>
                )}
                {source.keywordScore !== undefined && (
                  <Badge variant="outline" className="h-5 border-border/70 px-1.5 text-[10px] text-muted-foreground">
                    keyword {formatRawScore(source.keywordScore)}
                  </Badge>
                )}
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <ScoreBar label="rerank" value={source.rerankScore} />
                <ScoreBar label="embedding" value={source.embeddingScore} />
                <ScoreBar label="coverage" value={source.coverageScore} />
              </div>
            </div>
          </details>
        </div>
      )}
    </div>
  )
}

function MessageBubble({ message }: { message: Message }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-tr-md bg-primary px-4 py-3 text-primary-foreground">
          <p className="whitespace-pre-wrap text-sm">{message.content}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[90%] space-y-3">
        <div className="rounded-2xl rounded-tl-md border border-border/50 bg-[#353535] px-4 py-3">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
            {message.content}
          </p>
        </div>
        {message.agent && <AgentTracePanel agent={message.agent} />}
      </div>
    </div>
  )
}

function EvidencePanel({ sources }: { sources: Source[] }) {
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set(["src-0"]))
  const [filter, setFilter] = useState<"all" | "high" | "medium">("all")

  const toggleSource = (sourceId: string) => {
    setExpandedSources((prev) => {
      const next = new Set(prev)
      if (next.has(sourceId)) {
        next.delete(sourceId)
      } else {
        next.add(sourceId)
      }
      return next
    })
  }

  const filteredSources = sources.filter((source) => {
    if (filter === "all") return true
    return source.credibility === filter
  })

  return (
    <aside className="hidden w-[380px] shrink-0 border-l border-border bg-card/30 lg:flex lg:flex-col">
      <div className="border-b border-border p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-foreground">证据来源</h2>
            <p className="text-xs text-muted-foreground">支撑上一条回答的文献片段</p>
          </div>
          <Badge variant="outline" className="border-primary/20 bg-primary/10 text-primary">
            {sources.length} 条来源
          </Badge>
        </div>
        <div className="mt-3 flex rounded-lg border border-border/50 bg-secondary/30 p-1">
          {(["all", "high", "medium"] as const).map((item) => (
            <button
              key={item}
              onClick={() => setFilter(item)}
              className={cn(
                "flex-1 rounded-md px-2 py-1.5 text-xs capitalize transition-colors",
                filter === item
                  ? "bg-primary/15 text-primary"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {filteredSources.length > 0 ? (
          filteredSources.map((source, index) => (
            <EvidenceCard
              key={source.id}
              source={source}
              index={index}
              isExpanded={expandedSources.has(source.id)}
              onToggle={() => toggleSource(source.id)}
            />
          ))
        ) : (
          <div className="rounded-lg border border-dashed border-border/70 p-4 text-center text-xs text-muted-foreground">
            {sources.length === 0 ? "上一条回答没有返回来源片段。" : "当前筛选条件下没有证据片段。"}
          </div>
        )}
      </div>
    </aside>
  )
}

export default function ChatPage({
  selectedDocumentId = null,
  onDocumentScopeChange,
  initialQuestion = null,
  onInitialQuestionConsumed,
}: ChatPageProps) {
  const [messages, setMessages] = useState<Message[]>(initialMessages)
  const [input, setInput] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [documents, setDocuments] = useState<ApiDocument[]>([])
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(false)
  const [sessionId] = useState(() => `session-${Date.now()}`)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const latestSources =
    [...messages].reverse().find((message) => message.role === "assistant" && message.sources !== undefined)?.sources ||
    []

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  useEffect(() => {
    if (!initialQuestion) return
    setInput(initialQuestion)
    textareaRef.current?.focus()
    onInitialQuestionConsumed?.()
  }, [initialQuestion, onInitialQuestionConsumed])

  useEffect(() => {
    setIsLoadingDocuments(true)
    fetch(`${API_BASE_URL}/api/documents`, { cache: "no-store" })
      .then((res) => res.json())
      .then((data) => {
        const parsedDocuments = ((data?.documents || []) as ApiDocument[]).filter(
          (document) => document.status === "parsed" && document.chunk_count > 0,
        )
        setDocuments(parsedDocuments)
      })
      .catch((err) => console.error("Failed to load documents:", err))
      .finally(() => setIsLoadingDocuments(false))
  }, [])

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/history?session_id=${sessionId}`)
      .then((res) => res.json())
      .then((data) => {
        if (data && data.length > 0) {
          const historyMessages: Message[] = data.map((entry: any) => ({
            id: `hist-${entry.timestamp}-${entry.role}`,
            role: entry.role,
            content: entry.content,
            sources: extractApiChunks(entry).map((chunk: ApiChunk, index: number) => toSource(chunk, index)),
          }))
          setMessages((prev) => [...prev, ...historyMessages])
        }
      })
      .catch((err) => console.error("Failed to load chat history:", err))
  }, [sessionId])

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!input.trim() || isLoading) return

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content: input.trim(),
    }

    setMessages((prev) => [...prev, userMessage])
    setInput("")
    setIsLoading(true)

    try {
      const res = await fetch(`${API_BASE_URL}/api/agent/research`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: userMessage.content,
          top_k: 5,
          session_id: sessionId,
          document_id: selectedDocumentId || undefined,
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data?.detail || "Backend request failed")
      }

      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: data.answer || "No answer yet.",
        sources: extractApiChunks(data).map((chunk: ApiChunk, index: number) => toSource(chunk, index)),
        agent: data.agent,
      }

      setMessages((prev) => [...prev, assistantMessage])
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Backend request failed"
      setMessages((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          content: `Warning: ${errorMessage}`,
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  const handleClear = () => {
    setMessages(initialMessages)
  }

  const handleExport = () => {
    const content = messages
      .map((message) => `[${message.role === "user" ? "User" : "ZhiYu"}]\n${message.content}`)
      .join("\n\n---\n\n")
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = `zhiyu-chat-history_${new Date().toLocaleDateString()}.txt`
    link.click()
    URL.revokeObjectURL(url)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      void handleSubmit()
    }
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="shrink-0 border-b border-border bg-card/50 backdrop-blur-sm">
        <div className="flex min-h-14 flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-sm font-semibold text-foreground">Research Agent</h1>
            <p className="text-xs text-muted-foreground">Summarize, compare, search, and draft literature reviews with citations.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-2 rounded-lg border border-border/50 bg-secondary/40 px-2 py-1.5">
              <FileText className="h-4 w-4 text-primary" />
              <Select
                value={selectedDocumentId ? String(selectedDocumentId) : ALL_DOCUMENTS_SCOPE}
                onValueChange={(value) => {
                  onDocumentScopeChange?.(value === ALL_DOCUMENTS_SCOPE ? null : Number(value))
                }}
              >
                <SelectTrigger className="h-8 w-[230px] border-0 bg-transparent px-1 shadow-none focus:ring-0">
                  <SelectValue placeholder={isLoadingDocuments ? "Loading documents..." : "All documents"} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL_DOCUMENTS_SCOPE}>All documents</SelectItem>
                  {documents.map((document) => (
                    <SelectItem key={document.id} value={String(document.id)}>
                      {getDocumentDisplayName(document)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button variant="ghost" size="sm" onClick={handleExport} className="h-8 gap-1 text-xs">
              <Download className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Export</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleClear}
              className="h-8 gap-1 text-xs text-destructive hover:text-destructive"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Clear</span>
            </Button>
          </div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex-1 space-y-4 overflow-y-auto p-4">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-tl-md border border-border/50 bg-card px-4 py-3">
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-2 animate-pulse rounded-full bg-primary" />
                    <div className="delay-150 h-2 w-2 animate-pulse rounded-full bg-primary" />
                    <div className="delay-300 h-2 w-2 animate-pulse rounded-full bg-primary" />
                    <span className="ml-2 text-xs text-muted-foreground">Planning, retrieving, and writing...</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="shrink-0 border-t border-border bg-card/50 p-4">
            <form onSubmit={handleSubmit} className="mx-auto max-w-3xl">
              <div className="flex gap-2">
                <Textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Try: 这篇讲什么 / 对比两篇 / 帮我找相关研究 / 写一段综述"
                  className="min-h-[44px] max-h-32 resize-none border-border/50 bg-secondary/50 focus:border-primary"
                  rows={1}
                />
                <Button type="submit" size="icon" disabled={!input.trim() || isLoading} className="h-11 w-11 shrink-0 rounded-xl">
                  <Send className="h-4 w-4" />
                </Button>
              </div>
              <p className="mt-2 text-center text-xs text-muted-foreground">Press Enter to send, Shift + Enter for a new line</p>
            </form>
          </div>
        </main>

        <EvidencePanel sources={latestSources} />
      </div>
    </div>
  )
}
