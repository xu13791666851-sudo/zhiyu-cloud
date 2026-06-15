"use client"

import { useEffect, useMemo, useState } from "react"
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Clock,
  RefreshCw,
  SearchX,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"

interface EvaluationSummary {
  total_questions: number
  successful_answers: number
  success_rate: number | null
  avg_retrieval_latency_ms: number | null
  no_source_count: number
  dominant_task: string | null
}

interface EvaluationLog {
  id: number
  query: string
  task_label: string
  success: boolean
  result_count: number
  evidence_state: string
  cited_source_count: number
  retrieval_latency_ms: number | null
  total_latency_ms: number | null
  created_at: string | null
}

interface EvaluationResponse {
  summary: EvaluationSummary
  task_counts: Record<string, number>
  no_source_questions: EvaluationLog[]
  recent_logs: EvaluationLog[]
}

function formatLatency(value: number | null) {
  if (typeof value !== "number") return "-"
  if (value >= 1000) return `${(value / 1000).toFixed(1)} 秒`
  return `${value.toFixed(0)} ms`
}

function formatPercent(value: number | null) {
  if (typeof value !== "number") return "-"
  return `${Math.round(value * 100)}%`
}

function formatDate(value: string | null) {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export default function EvaluationPage() {
  const [data, setData] = useState<EvaluationResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadEvaluation = () => {
    setIsLoading(true)
    setError(null)
    fetch(`${API_BASE_URL}/api/agent/evaluation?limit=200`, { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`请求失败：${res.status}`)
        return res.json()
      })
      .then((payload: EvaluationResponse) => setData(payload))
      .catch((err) => setError(err instanceof Error ? err.message : "评估数据加载失败"))
      .finally(() => setIsLoading(false))
  }

  useEffect(() => {
    loadEvaluation()
  }, [])

  const taskEntries = useMemo(() => Object.entries(data?.task_counts || {}), [data])
  const maxTaskCount = Math.max(1, ...taskEntries.map(([, count]) => count))
  const summary = data?.summary

  return (
    <div className="min-h-screen overflow-y-auto p-4 md:p-6">
      <header className="mb-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Agent 评估</h1>
          <p className="text-sm text-muted-foreground">
            观察最近的任务识别、检索效果、来源覆盖和响应耗时
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={loadEvaluation} disabled={isLoading} className="gap-2">
          <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
          刷新
        </Button>
      </header>

      {error && (
        <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <section className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={Activity} label="最近提问" value={summary?.total_questions ?? 0} hint="Agent 记录数" />
        <MetricCard icon={CheckCircle2} label="成功回答" value={summary?.successful_answers ?? 0} hint={`成功率 ${formatPercent(summary?.success_rate ?? null)}`} />
        <MetricCard icon={Clock} label="平均检索耗时" value={formatLatency(summary?.avg_retrieval_latency_ms ?? null)} hint="只统计检索阶段" />
        <MetricCard icon={SearchX} label="未找到来源" value={summary?.no_source_count ?? 0} hint={summary?.dominant_task ? `常见任务：${summary.dominant_task}` : "暂无任务分布"} />
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <section className="space-y-5">
          <Card className="border-border/50 bg-card/50">
            <CardContent className="p-4">
              <div className="mb-4 flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-primary" />
                <h2 className="text-sm font-semibold text-foreground">Agent 任务分布</h2>
              </div>
              {taskEntries.length > 0 ? (
                <div className="space-y-3">
                  {taskEntries.map(([task, count]) => (
                    <div key={task} className="space-y-1.5">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-foreground">{task}</span>
                        <span className="text-muted-foreground">{count}</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-secondary">
                        <div
                          className="h-full rounded-full bg-primary"
                          style={{ width: `${Math.max(8, (count / maxTaskCount) * 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState text="还没有 Agent 任务记录。" />
              )}
            </CardContent>
          </Card>

          <Card className="border-border/50 bg-card/50">
            <CardContent className="p-4">
              <div className="mb-4 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-yellow-400" />
                <h2 className="text-sm font-semibold text-foreground">未找到来源的问题</h2>
              </div>
              {data?.no_source_questions?.length ? (
                <div className="space-y-2">
                  {data.no_source_questions.map((item) => (
                    <LogRow key={item.id} item={item} compact />
                  ))}
                </div>
              ) : (
                <EmptyState text="最近没有未找到来源的问题。" />
              )}
            </CardContent>
          </Card>
        </section>

        <Card className="border-border/50 bg-card/50">
          <CardContent className="p-4">
            <div className="mb-4 flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold text-foreground">最近 Agent 记录</h2>
            </div>
            {data?.recent_logs?.length ? (
              <div className="space-y-2">
                {data.recent_logs.map((item) => (
                  <LogRow key={item.id} item={item} />
                ))}
              </div>
            ) : (
              <EmptyState text="暂无最近记录。" />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function MetricCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: typeof Activity
  label: string
  value: string | number
  hint: string
}) {
  return (
    <Card className="border-border/50 bg-card/50">
      <CardContent className="p-4">
        <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="h-4 w-4" />
        </div>
        <div className="text-2xl font-semibold text-foreground">{value}</div>
        <div className="mt-1 text-sm text-muted-foreground">{label}</div>
        <div className="mt-2 text-xs text-muted-foreground/80">{hint}</div>
      </CardContent>
    </Card>
  )
}

function LogRow({ item, compact = false }: { item: EvaluationLog; compact?: boolean }) {
  return (
    <div className="rounded-lg border border-border/50 bg-background/30 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <Badge variant="outline" className="border-primary/20 bg-primary/10 text-primary">
          {item.task_label}
        </Badge>
        <Badge variant="outline" className={item.result_count > 0 ? "border-green-500/20 text-green-400" : "border-yellow-500/20 text-yellow-400"}>
          {item.evidence_state}
        </Badge>
      </div>
      <p className="line-clamp-2 text-sm leading-relaxed text-foreground">{item.query}</p>
      {!compact && (
        <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
          <span>{formatDate(item.created_at)}</span>
          <span>{item.result_count} 条来源</span>
          <span>检索 {formatLatency(item.retrieval_latency_ms)}</span>
          <span>总耗时 {formatLatency(item.total_latency_ms)}</span>
        </div>
      )}
    </div>
  )
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border/70 p-4 text-center text-sm text-muted-foreground">
      {text}
    </div>
  )
}
