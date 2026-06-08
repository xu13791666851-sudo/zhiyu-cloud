"use client"

import { useState, useCallback } from "react"
import {
  Search,
  Upload,
  FileText,
  CheckCircle2,
  Clock,
  XCircle,
  Trash2,
  Eye,
  MoreVertical,
  FolderOpen,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"

interface Document {
  id: string
  name: string
  status: "parsed" | "parsing" | "failed"
  uploadedAt: string
  size: string
  type: string
  chunks?: number
}

const statusConfig = {
  parsed: {
    label: "已解析",
    icon: CheckCircle2,
    className: "bg-green-500/10 text-green-400 border-green-500/20",
  },
  parsing: {
    label: "解析中",
    icon: Clock,
    className: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  },
  failed: {
    label: "解析失败",
    icon: XCircle,
    className: "bg-red-500/10 text-red-400 border-red-500/20",
  },
}

const initialDocuments: Document[] = [
  {
    id: "1",
    name: "深圳国贸大厦滑模施工技术.pdf",
    status: "parsed",
    uploadedAt: "2026-05-01",
    size: "2.3 MB",
    type: "PDF",
    chunks: 45,
  },
  {
    id: "2",
    name: "深圳建筑发展史.pdf",
    status: "parsed",
    uploadedAt: "2026-05-01",
    size: "5.8 MB",
    type: "PDF",
    chunks: 128,
  },
  {
    id: "3",
    name: "举一纲而万目张_华侨城现象.pdf",
    status: "parsed",
    uploadedAt: "2026-05-02",
    size: "1.2 MB",
    type: "PDF",
    chunks: 32,
  },
  {
    id: "4",
    name: "从规划体系到规划制度.pdf",
    status: "parsed",
    uploadedAt: "2026-05-02",
    size: "3.1 MB",
    type: "PDF",
    chunks: 67,
  },
  {
    id: "5",
    name: "深圳市城市设计历程回顾与思考.pdf",
    status: "parsed",
    uploadedAt: "2026-05-03",
    size: "2.7 MB",
    type: "PDF",
    chunks: 54,
  },
  {
    id: "6",
    name: "深圳南头古城研究.pdf",
    status: "parsed",
    uploadedAt: "2026-05-03",
    size: "1.8 MB",
    type: "PDF",
    chunks: 41,
  },
  {
    id: "7",
    name: "深圳历史建筑遗产调查报告.pdf",
    status: "parsed",
    uploadedAt: "2026-05-04",
    size: "8.5 MB",
    type: "PDF",
    chunks: 186,
  },
  {
    id: "8",
    name: "蛇口工业区房产经营改革.pdf",
    status: "parsed",
    uploadedAt: "2026-05-04",
    size: "1.5 MB",
    type: "PDF",
    chunks: 38,
  },
  {
    id: "9",
    name: "深圳特区建筑风格演变研究.pdf",
    status: "parsing",
    uploadedAt: "2026-05-05",
    size: "4.2 MB",
    type: "PDF",
  },
  {
    id: "10",
    name: "华侨城规划理念分析.docx",
    status: "parsed",
    uploadedAt: "2026-05-05",
    size: "856 KB",
    type: "Word",
    chunks: 28,
  },
]

function DocumentCard({
  document,
  onDelete,
  onPreview,
}: {
  document: Document
  onDelete: (id: string) => void
  onPreview: (doc: Document) => void
}) {
  const config = statusConfig[document.status]
  const StatusIcon = config.icon

  return (
    <Card className="border-border/50 bg-card/50 transition-all hover:border-border hover:bg-card">
      <CardContent className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3 min-w-0 flex-1">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FileText className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-medium text-foreground line-clamp-2 sm:truncate">
                {document.name}
              </h3>
              <div className="mt-1 flex flex-col gap-1 text-xs text-muted-foreground sm:flex-row sm:flex-wrap sm:items-center sm:gap-2">
                <span>{document.size}</span>
                <span className="hidden sm:inline">·</span>
                <span>{document.uploadedAt}</span>
                {document.chunks && (
                  <>
                    <span className="hidden sm:inline">·</span>
                    <span>{document.chunks} 文本块</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between gap-2 sm:shrink-0 sm:justify-end">
            <Badge variant="outline" className={cn("text-xs", config.className)}>
              <StatusIcon className="mr-1 h-3 w-3" />
              {config.label}
            </Badge>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => onPreview(document)}>
                  <Eye className="mr-2 h-4 w-4" />
                  预览
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => onDelete(document.id)}
                  className="text-destructive focus:text-destructive"
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  删除
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>(initialDocuments)
  const [searchQuery, setSearchQuery] = useState("")
  const [isDragging, setIsDragging] = useState(false)
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null)

  const filteredDocuments = documents.filter((doc) =>
    doc.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const stats = {
    total: documents.length,
    parsed: documents.filter((d) => d.status === "parsed").length,
    chunks: documents.reduce((sum, d) => sum + (d.chunks || 0), 0),
  }

  const handleDelete = (id: string) => {
    setDocuments((prev) => prev.filter((doc) => doc.id !== id))
  }

  const handlePreview = (doc: Document) => {
    setPreviewDoc(doc)
  }

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)

    const files = Array.from(e.dataTransfer.files)
    files.forEach((file) => {
      const newDoc: Document = {
        id: `new-${Date.now()}-${Math.random()}`,
        name: file.name,
        status: "parsing",
        uploadedAt: new Date().toISOString().split("T")[0],
        size: `${(file.size / 1024 / 1024).toFixed(1)} MB`,
        type: file.name.endsWith(".pdf") ? "PDF" : "Word",
      }
      setDocuments((prev) => [newDoc, ...prev])

      // Simulate parsing completion
      setTimeout(() => {
        setDocuments((prev) =>
          prev.map((doc) =>
            doc.id === newDoc.id
              ? { ...doc, status: "parsed" as const, chunks: Math.floor(Math.random() * 50) + 20 }
              : doc
          )
        )
      }, 3000)
    })
  }, [])

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    files.forEach((file) => {
      const newDoc: Document = {
        id: `new-${Date.now()}-${Math.random()}`,
        name: file.name,
        status: "parsing",
        uploadedAt: new Date().toISOString().split("T")[0],
        size: `${(file.size / 1024 / 1024).toFixed(1)} MB`,
        type: file.name.endsWith(".pdf") ? "PDF" : "Word",
      }
      setDocuments((prev) => [newDoc, ...prev])

      setTimeout(() => {
        setDocuments((prev) =>
          prev.map((doc) =>
            doc.id === newDoc.id
              ? { ...doc, status: "parsed" as const, chunks: Math.floor(Math.random() * 50) + 20 }
              : doc
          )
        )
      }, 3000)
    })
    e.target.value = ""
  }

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <header className="shrink-0 border-b border-border bg-card/50 backdrop-blur-sm">
        <div className="px-4 py-4">
          <h1 className="text-lg font-semibold text-foreground">文献管理</h1>
          <p className="text-sm text-muted-foreground">
            管理知识库中的文献资料
          </p>
        </div>
      </header>

      {/* Stats */}
      <div className="shrink-0 border-b border-border/50 bg-card/30 px-4 py-3">
        <div className="flex items-center gap-6 text-sm">
          <div className="flex items-center gap-2">
            <FolderOpen className="h-4 w-4 text-primary" />
            <span className="text-muted-foreground">文献总数：</span>
            <span className="font-medium text-foreground">{stats.total}</span>
          </div>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-green-400" />
            <span className="text-muted-foreground">已解析：</span>
            <span className="font-medium text-foreground">{stats.parsed}</span>
          </div>
          <div className="hidden sm:flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" />
            <span className="text-muted-foreground">文本片段：</span>
            <span className="font-medium text-foreground">{stats.chunks}</span>
          </div>
        </div>
      </div>

      {/* Search and Upload */}
      <div className="shrink-0 px-4 py-3 border-b border-border/50">
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索文献名称..."
              className="pl-9 bg-secondary/50 border-border/50"
            />
          </div>
          <label>
            <input
              type="file"
              accept=".pdf,.doc,.docx"
              multiple
              onChange={handleFileInput}
              className="hidden"
            />
            <Button asChild className="cursor-pointer gap-2">
              <span>
                <Upload className="h-4 w-4" />
                <span className="hidden sm:inline">上传文献</span>
              </span>
            </Button>
          </label>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* Drop Zone */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={cn(
            "mb-4 rounded-xl border-2 border-dashed p-6 text-center transition-all",
            isDragging
              ? "border-primary bg-primary/5"
              : "border-border/50 hover:border-border"
          )}
        >
          <Upload
            className={cn(
              "mx-auto h-8 w-8 mb-2",
              isDragging ? "text-primary" : "text-muted-foreground"
            )}
          />
          <p className="text-sm text-muted-foreground">
            拖拽 PDF/Word 文件到此处上传
          </p>
          <p className="mt-1 text-xs text-muted-foreground/60">
            支持 PDF、DOC、DOCX 格式
          </p>
        </div>

        {/* Document List */}
        <div className="space-y-3">
          {filteredDocuments.length === 0 ? (
            <div className="py-12 text-center">
              <FileText className="mx-auto h-12 w-12 text-muted-foreground/50" />
              <p className="mt-4 text-sm text-muted-foreground">
                {searchQuery ? "未找到匹配的文献" : "暂无文献"}
              </p>
            </div>
          ) : (
            filteredDocuments.map((doc) => (
              <DocumentCard
                key={doc.id}
                document={doc}
                onDelete={handleDelete}
                onPreview={handlePreview}
              />
            ))
          )}
        </div>
      </div>

      {/* Preview Dialog */}
      <Dialog open={!!previewDoc} onOpenChange={() => setPreviewDoc(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              {previewDoc?.name}
            </DialogTitle>
            <DialogDescription>
              文献详情与解析状态
            </DialogDescription>
          </DialogHeader>
          {previewDoc && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="rounded-lg bg-secondary/50 p-3">
                  <p className="text-xs text-muted-foreground">文件大小</p>
                  <p className="text-sm font-medium text-foreground">
                    {previewDoc.size}
                  </p>
                </div>
                <div className="rounded-lg bg-secondary/50 p-3">
                  <p className="text-xs text-muted-foreground">上传时间</p>
                  <p className="text-sm font-medium text-foreground">
                    {previewDoc.uploadedAt}
                  </p>
                </div>
                <div className="rounded-lg bg-secondary/50 p-3">
                  <p className="text-xs text-muted-foreground">文件类型</p>
                  <p className="text-sm font-medium text-foreground">
                    {previewDoc.type}
                  </p>
                </div>
                <div className="rounded-lg bg-secondary/50 p-3">
                  <p className="text-xs text-muted-foreground">文本片段</p>
                  <p className="text-sm font-medium text-foreground">
                    {previewDoc.chunks || "-"}
                  </p>
                </div>
              </div>
              <div className="rounded-lg border border-border/50 bg-secondary/30 p-4">
                <p className="text-xs text-muted-foreground mb-2">解析状态</p>
                <Badge
                  variant="outline"
                  className={cn(
                    "text-sm",
                    statusConfig[previewDoc.status].className
                  )}
                >
                  {(() => {
                    const StatusIcon = statusConfig[previewDoc.status].icon
                    return <StatusIcon className="mr-1 h-4 w-4" />
                  })()}
                  {statusConfig[previewDoc.status].label}
                </Badge>
                {previewDoc.status === "parsed" && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    文献已成功解析并纳入知识库，可在问答中检索引用。
                  </p>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
