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
      .catch((err) => console.error("获取历史记录失败:", err))
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
        throw new Error(data?.detail || "后端服务调用失败")
      }

      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: data.answer || "暂无回答",
        sources: (data.chunks || []).map((chunk: ApiChunk, index: number) => toSource(chunk, index)),
      }

      setMessages((prev) => [...prev, assistantMessage])
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "后端服务调用失败"
      setMessages((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          content: `⚠️ ${errorMessage}`,
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
      .map((message) => `[${message.role === "user" ? "用户" : "知域"}]\n${message.content}`)
      .join("\n\n---\n\n")
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = `知域对话记录_${new Date().toLocaleDateString()}.txt`
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
            <h1 className="text-sm font-semibold text-foreground">智能问答</h1>
            <p className="text-xs text-muted-foreground">基于知识库与新上传文献的真实问答。</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={handleExport} className="h-8 gap-1 text-xs">
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
                <span className="ml-2 text-xs text-muted-foreground">正在检索与生成回答...</span>
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
              placeholder="输入你的问题..."
              className="min-h-[44px] max-h-32 resize-none border-border/50 bg-secondary/50 focus:border-primary"
              rows={1}
            />
            <Button type="submit" size="icon" disabled={!input.trim() || isLoading} className="h-11 w-11 shrink-0 rounded-xl">
              <Send className="h-4 w-4" />
            </Button>
          </div>
          <p className="mt-2 text-center text-xs text-muted-foreground">按 Enter 发送，Shift + Enter 换行</p>
        </form>
      </div>
    </div>
  )
}
