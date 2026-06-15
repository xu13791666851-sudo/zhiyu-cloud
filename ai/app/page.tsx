"use client"

import { useState } from "react"
import { BarChart3, Home, MessageSquare, FolderOpen } from "lucide-react"
import { cn } from "@/lib/utils"
import HomePage from "@/components/zhiyu/home-page"
import ChatPage from "@/components/zhiyu/chat-page"
import DocumentsPage from "@/components/zhiyu/documents-page"
import EvaluationPage from "@/components/zhiyu/evaluation-page"

type TabType = "home" | "chat" | "documents" | "evaluation"

export default function ZhiYuApp() {
  const [activeTab, setActiveTab] = useState<TabType>("home")
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(null)
  const [draftQuestion, setDraftQuestion] = useState<string | null>(null)

  const handleAskDocument = (documentId: number) => {
    setSelectedDocumentId(documentId)
    setActiveTab("chat")
  }

  const handleAskQuestion = (question: string) => {
    setDraftQuestion(question)
    setActiveTab("chat")
  }

  const tabs = [
    { id: "home" as const, label: "首页", icon: Home },
    { id: "chat" as const, label: "问答", icon: MessageSquare },
    { id: "documents" as const, label: "文献", icon: FolderOpen },
    { id: "evaluation" as const, label: "评估", icon: BarChart3 },
  ]

  const renderContent = () => {
    switch (activeTab) {
      case "home":
        return <HomePage onNavigate={setActiveTab} onAskQuestion={handleAskQuestion} />
      case "chat":
        return (
          <ChatPage
            selectedDocumentId={selectedDocumentId}
            onDocumentScopeChange={setSelectedDocumentId}
            initialQuestion={draftQuestion}
            onInitialQuestionConsumed={() => setDraftQuestion(null)}
          />
        )
      case "documents":
        return <DocumentsPage onAskDocument={handleAskDocument} />
      case "evaluation":
        return <EvaluationPage />
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* Desktop Sidebar Navigation */}
      <nav className="fixed left-0 top-0 z-50 hidden h-full w-20 flex-col border-r border-border bg-card/95 backdrop-blur-lg md:flex lg:w-64">
        <div className="flex h-16 items-center justify-center border-b border-border px-4 lg:justify-start">
          <div className="flex items-center gap-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <span className="text-lg font-bold">知</span>
            </div>
            <div className="hidden lg:block">
              <h1 className="text-lg font-bold text-foreground">知域</h1>
              <p className="text-xs text-muted-foreground">ZhiYu</p>
            </div>
          </div>
        </div>
        <div className="flex flex-1 flex-col gap-2 p-3">
          {tabs.map((tab) => {
            const Icon = tab.icon
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  "flex items-center gap-3 rounded-xl px-3 py-3 transition-all duration-200 lg:px-4",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                )}
              >
                <Icon className="h-5 w-5" />
                <span className="hidden text-sm font-medium lg:block">
                  {tab.label}
                </span>
              </button>
            )
          })}
        </div>
      </nav>

      {/* Main Content Area - Mobile */}
      <main className="flex-1 pb-16 md:hidden">
        {renderContent()}
      </main>

      {/* Main Content Area - Desktop */}
      <main className="hidden min-h-screen md:block md:pl-20 lg:pl-64">
        {renderContent()}
      </main>

      {/* Mobile Bottom Tab Bar */}
      <nav className="fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-card/95 backdrop-blur-lg md:hidden">
        <div className="mx-auto flex h-16 max-w-lg items-center justify-around px-4">
          {tabs.map((tab) => {
            const Icon = tab.icon
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  "flex flex-col items-center justify-center gap-1 rounded-lg px-4 py-2 transition-all duration-200",
                  isActive
                    ? "text-primary"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Icon className={cn("h-5 w-5", isActive && "scale-110")} />
                <span className="text-xs font-medium">{tab.label}</span>
              </button>
            )
          })}
        </div>
      </nav>
    </div>
  )
}
