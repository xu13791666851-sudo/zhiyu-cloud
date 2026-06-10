"use client"

import { useEffect, useRef, useState } from "react"
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Download,
  FileText,
  Send,
  Trash2,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
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
}

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  sources?: Source[]
}

interface ApiChunk {
  content: string
  doc?: string
  credibility?: "high" | "medium" | "low"
  page_start?: number | null
  page_end?: number | null
  source_type?: string | null
  section_title?: string | null
}

const credibilityConfig = {
  high: {
    label: "楂樺彲淇″害",
    icon: CheckCircle2,
    className: "bg-green-500/10 text-green-400 border-green-500/20",
  },
  medium: {
    label: "涓彲淇″害",
    icon: AlertTriangle,
    className: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  },
  low: {
    label: "浣庡彲淇″害",
    icon: AlertCircle,
    className: "bg-red-500/10 text-red-400 border-red-500/20",
  },
}

const initialMessages: Message[] = [
  {
    id: "welcome",
    role: "assistant",
    content:
      "浣犲ソ锛屾垜鏄煡鍩?AI 鏂囩尞鍔╂墜銆傜幇鍦ㄦ垜浼氫紭鍏堜粠浣犳柊涓婁紶骞惰В鏋愭垚鍔熺殑鏂囩尞涓绱㈠唴瀹癸紝骞堕檮涓婃潵婧愮墖娈点€?,
  },
]

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"

function formatChunkPage(chunk: ApiChunk) {
  if (!chunk.page_start) return ""
  if (!chunk.page_end || chunk.page_end === chunk.page_start) {
    return `p. ${chunk.page_start}`
  }
  return `pp. ${chunk.page_start}-${chunk.page_end}`
}

function toSource(chunk: ApiChunk, index: number): Source {
  const sectionSuffix = chunk.section_title ? ` / ${chunk.section_title}` : ""
  return {
    id: `src-${index}`,
    title: `${chunk.doc || "鏈煡鏉ユ簮"}${sectionSuffix}`,
    author: "",
    year: "",
    page: formatChunkPage(chunk),
    excerpt: chunk.content?.slice(0, 140) || "",
    credibility: chunk.credibility || "medium",
    type: chunk.source_type || "",
  }
}

function SourceCard({
  source,
  isExpanded,
  onToggle,
}: {
  source: Source
  isExpanded: boolean
  onToggle: () => void
}) {
  const config = credibilityConfig[source.credibility]
  const Icon = config.icon

  return (
    <div className="overflow-hidden rounded-lg border border-border/50 bg-secondary/30">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-2 p-3 text-left transition-colors hover:bg-secondary/50"
      >
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <FileText className="h-4 w-4 shrink-0 text-primary" />
          <span className="truncate text-sm font-medium text-foreground">{source.title}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
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
        <div className="space-y-2 border-t border-border/50 p-3">
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            {source.author && <span>浣滆€? {source.author}</span>}
            {source.page && <span>{source.page}</span>}
            {source.type && <span>{source.type}</span>}
          </div>
          <div className="rounded bg-secondary/50 p-2 text-xs italic text-foreground/80">
            "{source.excerpt}"
          </div>
        </div>
      )}
    </div>
  )
}

function MessageBubble({ message }: { message: Message }) {
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set())

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

        {message.sources && message.sources.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground">
              鍙傝€冩潵婧?({message.sources.length})
            </p>
            {message.sources.map((source) => (
              <SourceCard
                key={source.id}
                source={source}
                isExpanded={expandedSources.has(source.id)}
                onToggle={() => toggleSource(source.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>(initialMessages)
  const [input, setInput] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [sessionId] = useState(() => `session-${Date.now()}`)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/history?session_id=${sessionId}`)
      .then((res) => res.json())
      .then((data) => {
        if (data && data.length > 0) {
          const historyMessages: Message[] = data.map((entry: any) => ({
            id: `hist-${entry.timestamp}-${entry.role}`,
            role: entry.role,
            content: entry.content,
            sources: (entry.sources || []).map((chunk: ApiChunk, index: number) => toSource(chunk, index)),
          }))
          setMessages((prev) => [...prev, ...historyMessages])
        }
      })
      .catch((err) => console.error("鑾峰彇鍘嗗彶璁板綍澶辫触:", err))
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
      const res = await fetch(`${API_BASE_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: userMessage.content,
          top_k: 5,
          session_id: sessionId,
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data?.detail || "鍚庣鏈嶅姟璋冪敤澶辫触")
      }

      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: data.answer || "鏆傛棤鍥炵瓟",
        sources: (data.chunks || []).map((chunk: ApiChunk, index: number) => toSource(chunk, index)),
      }

      setMessages((prev) => [...prev, assistantMessage])
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "鍚庣鏈嶅姟璋冪敤澶辫触"
      setMessages((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          content: `鈿狅笍 ${errorMessage}`,
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
      .map((message) => `[${message.role === "user" ? "鐢ㄦ埛" : "鐭ュ煙"}]\n${message.content}`)
      .join("\n\n---\n\n")
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = `鐭ュ煙瀵硅瘽璁板綍_${new Date().toLocaleDateString()}.txt`
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
        <div className="flex h-14 items-center justify-between px-4">
          <div>
            <h1 className="text-sm font-semibold text-foreground">鏅鸿兘闂瓟</h1>
            <p className="text-xs text-muted-foreground">鍩轰簬鐭ヨ瘑搴撲笌鏂颁笂浼犳枃鐚殑鐪熷疄闂瓟銆?/p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={handleExport} className="h-8 gap-1 text-xs">
              <Download className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">瀵煎嚭</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleClear}
              className="h-8 gap-1 text-xs text-destructive hover:text-destructive"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">娓呯┖</span>
            </Button>
          </div>
        </div>
      </header>

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
                <span className="ml-2 text-xs text-muted-foreground">姝ｅ湪妫€绱笌鐢熸垚鍥炵瓟...</span>
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
              placeholder="杈撳叆浣犵殑闂..."
              className="min-h-[44px] max-h-32 resize-none border-border/50 bg-secondary/50 focus:border-primary"
              rows={1}
            />
            <Button type="submit" size="icon" disabled={!input.trim() || isLoading} className="h-11 w-11 shrink-0 rounded-xl">
              <Send className="h-4 w-4" />
            </Button>
          </div>
          <p className="mt-2 text-center text-xs text-muted-foreground">鎸?Enter 鍙戦€侊紝Shift + Enter 鎹㈣</p>
        </form>
      </div>
    </div>
  )
}
