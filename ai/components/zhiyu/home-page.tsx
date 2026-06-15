"use client"

import { Upload, MessageSquare, Link2, Search, BookOpen, ListChecks, ArrowRight, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

type TabType = "home" | "chat" | "documents"

interface HomePageProps {
  onNavigate: (tab: TabType) => void
}

const features = [
  {
    icon: Upload,
    title: "上传文献",
    description: "支持 PDF、Word、文本上传与自动解析",
  },
  {
    icon: ListChecks,
    title: "任务识别",
    description: "自动判断摘要、对比、检索或综述任务",
  },
  {
    icon: Search,
    title: "全库检索",
    description: "从已解析文献中查找相关研究片段",
  },
  {
    icon: BookOpen,
    title: "文献摘要",
    description: "快速梳理论文主题、方法与核心结论",
  },
  {
    icon: MessageSquare,
    title: "多文献对比",
    description: "对比不同文献的观点、方法和研究对象",
  },
  {
    icon: Link2,
    title: "引用综述",
    description: "生成带来源引用的建筑学文献综述",
  },
]

const suggestedQuestions = [
  "深圳国贸大厦的滑模施工技术有什么特点？",
  "深圳华侨城片区的规划建设主导者是谁？",
  "南头古城城墙的建造年代有哪几种说法？",
]

export default function HomePage({ onNavigate }: HomePageProps) {
  return (
    <div className="min-h-screen overflow-y-auto">
      {/* Hero Section */}
      <section className="relative overflow-hidden px-4 py-12 md:px-8 md:py-20">
        {/* Background Gradient */}
        <div className="absolute inset-0 -z-10">
          <div className="absolute left-1/2 top-0 h-[500px] w-[800px] -translate-x-1/2 rounded-full bg-primary/10 blur-3xl" />
        </div>

        <div className="mx-auto max-w-4xl text-center">
          {/* Logo */}
          <div className="mb-6 inline-flex items-center gap-3 rounded-full bg-card/80 px-4 py-2 backdrop-blur-sm">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <span className="text-sm font-bold">知</span>
            </div>
            <span className="text-sm font-medium text-muted-foreground">
              ZHIYU · AI 学术文献助手
            </span>
          </div>

          {/* Title */}
          <h1 className="mb-4 text-balance text-3xl font-bold tracking-tight text-foreground md:text-5xl">
            搭建一个真实可信的
            <span className="text-primary"> AI 文献助手</span>
          </h1>

          {/* Subtitle */}
          <p className="mb-8 text-pretty text-lg text-muted-foreground md:text-xl">
            让每个学术团队拥有自己的 AI 文献助手
          </p>

          {/* CTA Button */}
          <Button
            size="lg"
            onClick={() => onNavigate("chat")}
            className="group h-16 min-w-[280px] gap-3 rounded-full px-11 text-xl font-semibold shadow-lg shadow-primary/20 md:h-20 md:min-w-[360px] md:text-2xl"
          >
            <Sparkles className="h-6 w-6 md:h-7 md:w-7" />
            开始提问
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
          </Button>
        </div>
      </section>

      {/* Features Grid */}
      <section className="px-4 py-8 md:px-8">
        <div className="mx-auto max-w-5xl">
          <h2 className="mb-6 text-center text-2xl font-semibold text-foreground md:text-2xl">
            核心能力
          </h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 md:gap-4">
            {features.map((feature, index) => {
              const Icon = feature.icon
              return (
                <Card
                  key={index}
                  className="group cursor-default border-border/50 bg-[#353535] transition-all duration-300 hover:border-primary/50 hover:bg-card"
                  style={{ borderColor: '#000000' }}
                >
                  <CardContent className="p-4 md:p-6">
                    <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                      <Icon className="h-5 w-5" />
                    </div>
                    <h3 className="mb-1 text-sm font-semibold text-foreground md:text-base">
                      {feature.title}
                    </h3>
                    <p className="text-xs text-muted-foreground md:text-sm">
                      {feature.description}
                    </p>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </div>
      </section>

      {/* Quick Start Section */}
      <section className="px-4 py-8 md:px-8 md:py-12">
        <div className="mx-auto max-w-3xl">
          <Card className="border-border/50 bg-[#131212]">
            <CardContent className="p-6 md:p-8">
              <h2 className="mb-2 text-lg font-semibold text-foreground md:text-xl">
                💬 快速开始提问
              </h2>
              <p className="mb-6 text-sm text-muted-foreground">
                点击下方问题快速体验，或直接进入问答页面
              </p>

              {/* Quick Start Input */}
              <button
                onClick={() => onNavigate("chat")}
                className="mb-6 flex w-full items-center justify-between rounded-xl border border-border bg-secondary/50 px-4 py-3 text-left transition-colors hover:border-primary/50 hover:bg-secondary"
              >
                <span className="text-sm text-muted-foreground">
                  点击这里开始对话...
                </span>
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                  <ArrowRight className="h-4 w-4" />
                </div>
              </button>

              {/* Suggested Questions */}
              <div>
                <h3 className="mb-3 text-sm font-medium text-muted-foreground">
                  推荐问题：
                </h3>
                <div className="flex flex-col gap-2">
                  {suggestedQuestions.map((question, index) => (
                    <button
                      key={index}
                      onClick={() => onNavigate("chat")}
                      className="flex items-start gap-2 rounded-lg border border-border/50 bg-secondary/30 px-4 py-3 text-left text-sm text-foreground transition-all hover:border-primary/50 hover:bg-secondary"
                    >
                      <span className="text-primary">•</span>
                      <span className="line-clamp-2">{question}</span>
                    </button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Stats Section */}
      <section className="px-4 py-8 md:px-8 md:py-12">
        <div className="mx-auto max-w-3xl">
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-primary md:text-3xl">32</div>
              <div className="text-xs text-muted-foreground md:text-sm">精选文献</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-primary md:text-3xl">3秒</div>
              <div className="text-xs text-muted-foreground md:text-sm">快速响应</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-primary md:text-3xl">100%</div>
              <div className="text-xs text-muted-foreground md:text-sm">可溯源</div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border/50 px-4 py-6 text-center md:px-8">
        <p className="text-xs text-muted-foreground">
          知域 ZhiYu © 2026 · 腾讯 PCG 校园 AI 产品创意大赛参赛作品
        </p>
      </footer>
    </div>
  )
}
