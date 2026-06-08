"use client"

import { useState, useRef, useEffect } from "react"
import { Send, Trash2, Download, AlertCircle, CheckCircle2, AlertTriangle, FileText, ChevronDown, ChevronUp } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
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
  hasConflict?: boolean
  conflictSummary?: string
}

const credibilityConfig = {
  high: {
    label: "高可信度",
    icon: CheckCircle2,
    className: "bg-green-500/10 text-green-400 border-green-500/20",
  },
  medium: {
    label: "中可信度",
    icon: AlertTriangle,
    className: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  },
  low: {
    label: "低可信度",
    icon: AlertCircle,
    className: "bg-red-500/10 text-red-400 border-red-500/20",
  },
}

const initialMessages: Message[] = [
  {
    id: "welcome",
    role: "assistant",
    content: "你好！我是知域 AI 文献助手。我可以基于知识库中的 32 篇深圳近现代建筑遗产相关文献为你解答问题。每条回答都会标注参考来源和可信度判断。\n\n你可以问我关于深圳建筑史、城市规划、遗产保护等方面的问题。",
  },
]

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"

// Simulated responses for demo
const demoResponses: Record<string, Message> = {
  "滑模": {
    id: "response-1",
    role: "assistant",
    content: `深圳国贸大厦的滑模施工技术具有以下特点：

**1. 采用内外筒整体滑模方案**
针对主楼筒中筒结构体系的特点，大胆提出了内外筒整体滑模的方案，有利于结构整体性。

**2. 技术经济效果显著**
与传统支模现浇方法相比：
- 缩短工期 90 天
- 提高工效 30%
- 节约木材 1000 立方米
- 节约钢管等架设材料 200 吨

**3. 施工速度快**
施工速度最快达到三天一层，从第 5 层至第 50 层共 48 层的滑模施工，共计实际日历工期 98 天，平均每层耗用 2.04 天。

**4. 施工质量好**
- 垂直偏差仅为 2 厘米
- 混凝土外形尺寸实测 3000 点，优良率为 98%
- 混凝土试块强度 700 组，合格率 100%`,
    sources: [
      {
        id: "src-1",
        title: "深圳国贸大厦滑模施工技术",
        author: "张建华",
        year: "1986",
        page: "42-45",
        excerpt: "采用内外筒整体滑模方案...施工速度最快达到三天一层",
        credibility: "high",
        type: "学术专著（第一手）",
      },
      {
        id: "src-2",
        title: "深圳建筑发展史",
        author: "陈丽云",
        year: "2019",
        page: "112-115",
        excerpt: "滑模工艺在国贸大厦建设中首次大规模应用，创造了深圳速度",
        credibility: "high",
        type: "学术专著（第一手）",
      },
    ],
  },
  "华侨城": {
    id: "response-2",
    role: "assistant",
    content: `关于华侨城早期建设的规划主导者，存在**不同的说法和侧重点**，但并非核心矛盾，而是从不同角度描述。

**说法A：孟大强是城市设计理念的关键奠基人**
1986年华侨城采纳了孟大强提出的生态城区城市设计建议方案，选择了"依山就势"的城市空间格局。

**说法B：华侨城集团是规划实施的主导者与决策管理者**
不仅是控规的作用，更是因为华侨城集团"富于创造性的决策管理并加强城市设计工作"。

**说法C：境外专家主导规划编制**
1986年华侨城集团引进了总设计师编制总体规划，由境外机构的专家主导规划编制。

---

📌 **学术建议**：建议采用整合表述——"华侨城早期规划的核心理念由国际知名城市设计师孟大强提出，同时，华侨城集团作为开发主体进行了高水平的决策管理。"`,
    sources: [
      {
        id: "src-3",
        title: "举一纲而万目张:读识华侨城现象",
        author: "朱荣远",
        year: "2018",
        page: "23-28",
        excerpt: "1986年华侨城采纳了孟大强提出的生态城区城市设计建议方案",
        credibility: "high",
        type: "学术研究文章（一手）",
      },
      {
        id: "src-4",
        title: "从规划体系到规划制度",
        author: "王富海",
        year: "2015",
        page: "56-60",
        excerpt: "华侨城集团富于创造性的决策管理并加强城市设计工作",
        credibility: "medium",
        type: "综述性文献（二手）",
      },
      {
        id: "src-5",
        title: "深圳市城市设计历程回顾与思考",
        author: "司马晓",
        year: "2020",
        page: "78-82",
        excerpt: "1986年华侨城集团引进了总设计师编制总体规划",
        credibility: "medium",
        type: "综述性文献（二手）",
      },
    ],
    hasConflict: true,
    conflictSummary: "三篇文献从不同角度描述了规划主导者，朱荣远的文章可视为一手研究或权威转引；王富海和司马晓的文章属于综述性二手文献。",
  },
  "南头古城": {
    id: "response-3",
    role: "assistant",
    content: `关于南头古城城墙的建造年代，知识库中的文献存在**多种说法**：

**说法A：明代初期建造**
有文献认为南头古城最初建于明洪武年间（约1368-1398年），是为了防御海盗和倭寇入侵。

**说法B：清代康熙年间重建**
部分文献指出现存城墙主要为清康熙年间（1662-1722年）重建，此前曾多次修缮。

**说法C：始建于东晋**
有观点认为南头古城的历史可追溯至东晋时期，但最初的城防设施与现存城墙形制不同。

---

📌 **学术建议**：目前最严谨的表述为"南头古城城墙始建年代说法不一，现存城墙主体为明清时期构筑"，如需精确引用建议查阅《新安县志》等原始方志文献。`,
    sources: [
      {
        id: "src-6",
        title: "深圳南头古城研究",
        author: "李明",
        year: "2017",
        page: "34-38",
        excerpt: "南头古城最初建于明洪武年间，是为了防御海盗",
        credibility: "medium",
        type: "学术论文（二手）",
      },
      {
        id: "src-7",
        title: "深圳历史建筑遗产调查报告",
        author: "深圳市文物局",
        year: "2021",
        page: "12-15",
        excerpt: "现存城墙主要为清康熙年间重建",
        credibility: "high",
        type: "官方调查报告（一手）",
      },
    ],
    hasConflict: true,
    conflictSummary: "关于城墙始建年代，不同文献给出了明代、清代、东晋等多种说法，反映了历史文献记载的差异。",
  },
}

function SourceCard({ source, isExpanded, onToggle }: { source: Source; isExpanded: boolean; onToggle: () => void }) {
  const config = credibilityConfig[source.credibility]
  const Icon = config.icon

  return (
    <div className="rounded-lg border border-border/50 bg-secondary/30 overflow-hidden">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-2 p-3 text-left hover:bg-secondary/50 transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <FileText className="h-4 w-4 shrink-0 text-primary" />
          <span className="text-sm font-medium text-foreground truncate">
            {source.title}
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
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
        <div className="border-t border-border/50 p-3 space-y-2">
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span>作者：{source.author}</span>
            <span>·</span>
            <span>年份：{source.year}</span>
            <span>·</span>
            <span>页码：{source.page}</span>
          </div>
          <div className="text-xs text-muted-foreground">
            来源类型：{source.type}
          </div>
          <div className="mt-2 rounded bg-secondary/50 p-2 text-xs text-foreground/80 italic">
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
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[90%] space-y-3">
        <div className="rounded-2xl rounded-tl-md bg-[#353535] border border-border/50 px-4 py-3">
          <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">
            {message.content}
          </p>
        </div>

        {message.hasConflict && message.conflictSummary && (
          <Card className="border-yellow-500/20 bg-yellow-500/5">
            <CardContent className="p-3">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-yellow-400 mt-0.5" />
                <div>
                  <p className="text-xs font-medium text-yellow-400 mb-1">
                    矛盾信息识别
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {message.conflictSummary}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {message.sources && message.sources.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground">
              📎 参考来源 ({message.sources.length})
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

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // 组件加载时获取历史记录
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/history?session_id=${sessionId}`)
      .then(res => res.json())
      .then(data => {
        if (data && data.length > 0) {
          const msgs: Message[] = data.map((d: any) => ({
            id: `hist-${d.timestamp}`,
            role: d.role,
            content: d.content,
            sources: (d.sources || []).map((c: any, i: number) => ({
              id: `src-${i}`,
              title: c.doc || "未知来源",
              author: "",
              year: "",
              page: "",
              excerpt: c.content?.slice(0, 100) + "..." || "",
              credibility: c.credibility || "medium",
              type: "",
            })),
          }))
          setMessages(prev => [...prev, ...msgs])
        }
      })
      .catch(err => console.error("获取历史记录失败:", err))
  }, [])

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
          session_id: sessionId  // 新增
        }),
      })
      const data = await res.json()

      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: data.answer || "暂无回答",
        sources: (data.chunks || []).map((c: any, i: number) => ({
          id: `src-${i}`,
          title: c.doc || "未知来源",
          author: "",
          year: "",
          page: "",
          excerpt: c.content.slice(0, 100) + "...",
          credibility: c.credibility || "medium",
          type: "",
        })),
      }

      setMessages((prev) => [...prev, assistantMessage])
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          content: "⚠️ 后端服务调用失败，请检查 api_server.py 是否正常运行。",
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
      .map((m) => `[${m.role === "user" ? "用户" : "知域"}]\n${m.content}`)
      .join("\n\n---\n\n")
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `知域对话记录_${new Date().toLocaleDateString()}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <header className="shrink-0 border-b border-border bg-card/50 backdrop-blur-sm">
        <div className="flex h-14 items-center justify-between px-4">
          <div>
            <h1 className="text-sm font-semibold text-foreground">智能问答</h1>
            <p className="text-xs text-muted-foreground">
              基于知识库的智能问答 · 所有回答均标注参考来源
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleExport}
              className="h-8 gap-1 text-xs"
            >
              <Download className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">导出</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleClear}
              className="h-8 gap-1 text-xs text-destructive hover:text-destructive"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">清空</span>
            </Button>
          </div>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-tl-md bg-card border border-border/50 px-4 py-3">
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-primary animate-pulse" />
                <div className="h-2 w-2 rounded-full bg-primary animate-pulse delay-150" />
                <div className="h-2 w-2 rounded-full bg-primary animate-pulse delay-300" />
                <span className="text-xs text-muted-foreground ml-2">
                  正在检索知识库...
                </span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="shrink-0 border-t border-border bg-card/50 p-4">
        <form onSubmit={handleSubmit} className="mx-auto max-w-3xl">
          <div className="flex gap-2">
            <Textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入你的问题..."
              className="min-h-[44px] max-h-32 resize-none bg-secondary/50 border-border/50 focus:border-primary"
              rows={1}
            />
            <Button
              type="submit"
              size="icon"
              disabled={!input.trim() || isLoading}
              className="h-11 w-11 shrink-0 rounded-xl"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
          <p className="mt-2 text-center text-xs text-muted-foreground">
            按 Enter 发送，Shift + Enter 换行
          </p>
        </form>
      </div>
    </div>
  )
}
