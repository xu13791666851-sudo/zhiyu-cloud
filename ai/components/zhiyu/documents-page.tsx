"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Eye,
  ExternalLink,
  FileText,
  FolderOpen,
  Loader2,
  MessageSquare,
  MoreVertical,
  RefreshCw,
  Search,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"

type DocumentStatus = "parsed" | "processing" | "pending" | "failed"

interface ApiDocument {
  id: number
  title: string
  author: string | null
  year: string | null
  source_type: string | null
  file_name: string | null
  file_type: string | null
  file_url: string | null
  file_size: number | null
  status: DocumentStatus
  metadata: Record<string, unknown>
  chunk_count: number
  created_at: string | null
  updated_at: string | null
}

interface ApiDocumentChunk {
  id: number
  chunk_index: number
  content: string
  page_start: number | null
  page_end: number | null
  section_title: string | null
}

interface ApiResearchCard {
  [key: string]: unknown
}

const researchCardSections = [
  ["research_object", "研究对象"],
  ["core_question", "核心问题"],
  ["main_arguments", "主要观点"],
  ["method_or_material", "方法 / 材料 / 案例"],
  ["key_findings", "关键结论"],
  ["theoretical_contribution", "理论贡献"],
  ["research_value", "对研究的启发"],
  ["limitations", "局限或待确认处"],
] as const

const statusConfig: Record<
  DocumentStatus,
  {
    label: string
    icon: typeof CheckCircle2
    className: string
  }
> = {
  parsed: {
    label: "已解析",
    icon: CheckCircle2,
    className: "bg-green-500/10 text-green-400 border-green-500/20",
  },
  processing: {
    label: "解析中",
    icon: Clock,
    className: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  },
  pending: {
    label: "待处理",
    icon: Clock,
    className: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  },
  failed: {
    label: "解析失败",
    icon: XCircle,
    className: "bg-red-500/10 text-red-400 border-red-500/20",
  },
}

function formatFileSize(bytes: number | null) {
  if (!bytes || bytes <= 0) return "-"
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.max(bytes / 1024, 0.1).toFixed(1)} KB`
  return `${bytes} B`
}

function formatDate(value: string | null) {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function getDocumentDisplayName(document: ApiDocument) {
  return document.title || document.file_name || `Document ${document.id}`
}

function metadataString(document: ApiDocument, key: string) {
  const value = document.metadata?.[key]
  return typeof value === "string" ? value : ""
}

function metadataList(document: ApiDocument, key: string) {
  const value = document.metadata?.[key]
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean)
  }
  if (typeof value === "string") {
    return value
      .split(/[,，;；、\n]/)
      .map((item) => item.trim())
      .filter(Boolean)
  }
  return []
}

function metadataCard(document: ApiDocument) {
  const value = document.metadata?.research_card
  return value && typeof value === "object" && !Array.isArray(value) ? (value as ApiResearchCard) : null
}

function cardText(card: ApiResearchCard | null, key: string) {
  if (!card) return ""
  const value = card[key]
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean).join("；")
  }
  if (value === null || value === undefined) return ""
  return String(value).trim()
}

function splitInputList(value: string) {
  return value
    .split(/[,，;；、\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

async function parseError(response: Response) {
  try {
    const data = (await response.json()) as { detail?: string }
    return data.detail || `Request failed with status ${response.status}`
  } catch {
    return `Request failed with status ${response.status}`
  }
}

function DocumentCard({
  document,
  onDelete,
  onPreview,
  onAsk,
  deletingId,
}: {
  document: ApiDocument
  onDelete: (id: number) => void
  onPreview: (doc: ApiDocument) => void
  onAsk: (id: number) => void
  deletingId: number | null
}) {
  const config = statusConfig[document.status] ?? statusConfig.pending
  const StatusIcon = config.icon
  const category = metadataString(document, "category")
  const tags = metadataList(document, "tags").slice(0, 3)

  return (
    <Card className="border-border/50 bg-card/50 transition-all hover:border-border hover:bg-card">
      <CardContent className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 flex-1 items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FileText className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-medium text-foreground line-clamp-2 sm:truncate">
                {getDocumentDisplayName(document)}
              </h3>
              <div className="mt-1 flex flex-col gap-1 text-xs text-muted-foreground sm:flex-row sm:flex-wrap sm:items-center sm:gap-2">
                <span>{formatFileSize(document.file_size)}</span>
                <span className="hidden sm:inline">/</span>
                <span>{formatDate(document.created_at)}</span>
                <span className="hidden sm:inline">/</span>
                <span>{document.chunk_count} chunks</span>
              </div>
              {(document.author || document.source_type) && (
                <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
                  {document.author && <span>{document.author}</span>}
                  {document.source_type && <span>{document.source_type}</span>}
                </div>
              )}
              {(category || tags.length > 0) && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {category && (
                    <Badge variant="outline" className="border-primary/20 bg-primary/10 text-xs text-primary">
                      {category}
                    </Badge>
                  )}
                  {tags.map((tag) => (
                    <Badge key={tag} variant="outline" className="text-xs text-muted-foreground">
                      {tag}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between gap-2 sm:shrink-0 sm:justify-end">
            <Badge variant="outline" className={cn("text-xs", config.className)}>
              <StatusIcon className="mr-1 h-3 w-3" />
              {config.label}
            </Badge>

            <Button
              variant="outline"
              size="sm"
              className="h-8 gap-1.5 border-primary/20 bg-primary/10 px-2 text-xs text-primary hover:bg-primary/15"
              onClick={() => onAsk(document.id)}
              disabled={document.status !== "parsed" || document.chunk_count <= 0}
            >
              <MessageSquare className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">问这篇</span>
            </Button>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => onPreview(document)}>
                  <Eye className="mr-2 h-4 w-4" />
                  查看详情
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => onDelete(document.id)}
                  disabled={deletingId === document.id}
                  className="text-destructive focus:text-destructive"
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  {deletingId === document.id ? "删除中..." : "删除"}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default function DocumentsPage({ onAskDocument }: { onAskDocument?: (documentId: number) => void }) {
  const [documents, setDocuments] = useState<ApiDocument[]>([])
  const [searchQuery, setSearchQuery] = useState("")
  const [categoryFilter, setCategoryFilter] = useState("all")
  const [previewMode, setPreviewMode] = useState<"overview" | "card" | "chunks">("overview")
  const [isDragging, setIsDragging] = useState(false)
  const [previewDoc, setPreviewDoc] = useState<ApiDocument | null>(null)
  const [previewChunks, setPreviewChunks] = useState<ApiDocumentChunk[]>([])
  const [researchCard, setResearchCard] = useState<ApiResearchCard | null>(null)
  const [isLoadingPreviewChunks, setIsLoadingPreviewChunks] = useState(false)
  const [isLoadingResearchCard, setIsLoadingResearchCard] = useState(false)
  const [isGeneratingResearchCard, setIsGeneratingResearchCard] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isUploading, setIsUploading] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [isSavingMetadata, setIsSavingMetadata] = useState(false)
  const [categoryInput, setCategoryInput] = useState("")
  const [tagsInput, setTagsInput] = useState("")
  const [keywordsInput, setKeywordsInput] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [researchCardError, setResearchCardError] = useState<string | null>(null)

  const loadDocuments = useCallback(async () => {
    setIsLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents`, { cache: "no-store" })
      if (!response.ok) {
        throw new Error(await parseError(response))
      }
      const data = (await response.json()) as { documents?: ApiDocument[] }
      setDocuments(data.documents ?? [])
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载文档失败")
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadDocuments()
  }, [loadDocuments])

  useEffect(() => {
    if (!previewDoc) return
    setCategoryInput(metadataString(previewDoc, "category"))
    setTagsInput(metadataList(previewDoc, "tags").join("，"))
    setKeywordsInput(metadataList(previewDoc, "keywords").join("，"))
  }, [previewDoc])

  const categoryOptions = useMemo(() => {
    const values = new Set<string>()
    documents.forEach((doc) => {
      const category = metadataString(doc, "category")
      if (category) values.add(category)
    })
    return Array.from(values).sort((a, b) => a.localeCompare(b, "zh-CN"))
  }, [documents])

  const filteredDocuments = useMemo(
    () =>
      documents.filter((doc) => {
        const category = metadataString(doc, "category")
        if (categoryFilter !== "all" && category !== categoryFilter) {
          return false
        }
        const haystack = [
          getDocumentDisplayName(doc),
          doc.file_name ?? "",
          doc.author ?? "",
          doc.source_type ?? "",
          category,
          ...metadataList(doc, "tags"),
          ...metadataList(doc, "keywords"),
        ]
          .join(" ")
          .toLowerCase()
        return haystack.includes(searchQuery.toLowerCase())
      }),
    [documents, searchQuery, categoryFilter]
  )

  const stats = useMemo(
    () => ({
      total: documents.length,
      parsed: documents.filter((doc) => doc.status === "parsed").length,
      chunks: documents.reduce((sum, doc) => sum + (doc.chunk_count || 0), 0),
    }),
    [documents]
  )

  const uploadFiles = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return

      setIsUploading(true)
      setError(null)

      const uploaded: ApiDocument[] = []
      const failures: string[] = []

      for (const file of files) {
        const formData = new FormData()
        formData.append("file", file)
        formData.append("title", file.name.replace(/\.[^.]+$/, ""))

        try {
          const response = await fetch(`${API_BASE_URL}/api/documents/upload`, {
            method: "POST",
            body: formData,
          })
          if (!response.ok) {
            throw new Error(await parseError(response))
          }
          const data = (await response.json()) as { document: ApiDocument }
          uploaded.push(data.document)
        } catch (err) {
          failures.push(`${file.name}: ${err instanceof Error ? err.message : "上传失败"}`)
        }
      }

      if (uploaded.length > 0) {
        setDocuments((prev) => [...uploaded, ...prev])
      }
      if (failures.length > 0) {
        setError(failures.join(" | "))
      } else {
        setError(null)
      }

      setIsUploading(false)
      void loadDocuments()
    },
    [loadDocuments]
  )

  const handleDelete = useCallback(
    async (id: number) => {
      setDeletingId(id)
      try {
        const response = await fetch(`${API_BASE_URL}/api/documents/${id}`, {
          method: "DELETE",
        })
        if (!response.ok) {
          throw new Error(await parseError(response))
        }
        setDocuments((prev) => prev.filter((doc) => doc.id !== id))
        setPreviewDoc((prev) => (prev?.id === id ? null : prev))
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : "删除文档失败")
      } finally {
        setDeletingId(null)
      }
    },
    []
  )

  const loadPreviewChunks = useCallback(async (doc: ApiDocument) => {
    setPreviewChunks([])
    setPreviewError(null)
    if (doc.status !== "parsed" || doc.chunk_count <= 0) {
      return
    }

    setIsLoadingPreviewChunks(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/${doc.id}/chunks?limit=12`, {
        cache: "no-store",
      })
      if (!response.ok) {
        throw new Error(await parseError(response))
      }
      const data = (await response.json()) as { chunks?: ApiDocumentChunk[] }
      setPreviewChunks(data.chunks ?? [])
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : "加载解析片段失败")
    } finally {
      setIsLoadingPreviewChunks(false)
    }
  }, [])

  const loadResearchCard = useCallback(async (doc: ApiDocument) => {
    setResearchCard(metadataCard(doc))
    setResearchCardError(null)
    if (doc.status !== "parsed" || doc.chunk_count <= 0) {
      return
    }

    setIsLoadingResearchCard(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/${doc.id}/research-card`, {
        cache: "no-store",
      })
      if (response.status === 404) {
        setResearchCard(null)
        return
      }
      if (!response.ok) {
        throw new Error(await parseError(response))
      }
      const data = (await response.json()) as { research_card?: ApiResearchCard; document?: ApiDocument }
      setResearchCard(data.research_card ?? null)
      if (data.document) {
        setPreviewDoc(data.document)
        setDocuments((prev) => prev.map((item) => (item.id === data.document?.id ? data.document : item)))
      }
    } catch (err) {
      setResearchCardError(err instanceof Error ? err.message : "加载文献卡片失败")
    } finally {
      setIsLoadingResearchCard(false)
    }
  }, [])

  const handleGenerateResearchCard = useCallback(
    async (force = false) => {
      if (!previewDoc) return

      setIsGeneratingResearchCard(true)
      setResearchCardError(null)
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/documents/${previewDoc.id}/research-card?force=${force ? "true" : "false"}`,
          { method: "POST" }
        )
        if (!response.ok) {
          throw new Error(await parseError(response))
        }
        const data = (await response.json()) as { research_card?: ApiResearchCard; document?: ApiDocument }
        setResearchCard(data.research_card ?? null)
        if (data.document) {
          setDocuments((prev) => prev.map((item) => (item.id === data.document?.id ? data.document : item)))
          setPreviewDoc(data.document)
        }
        setPreviewMode("card")
      } catch (err) {
        setResearchCardError(err instanceof Error ? err.message : "生成文献卡片失败")
      } finally {
        setIsGeneratingResearchCard(false)
      }
    },
    [previewDoc]
  )

  const handlePreview = useCallback((doc: ApiDocument) => {
    setPreviewMode("overview")
    setPreviewDoc(doc)
    setResearchCard(metadataCard(doc))
    void loadPreviewChunks(doc)
    void loadResearchCard(doc)
  }, [loadPreviewChunks, loadResearchCard])

  const handleOpenDocumentFile = useCallback((doc: ApiDocument) => {
    window.open(`${API_BASE_URL}/api/documents/${doc.id}/file`, "_blank", "noopener,noreferrer")
  }, [])

  const handleSaveMetadata = useCallback(async () => {
    if (!previewDoc) return

    setIsSavingMetadata(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/${previewDoc.id}/metadata`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category: categoryInput.trim() || null,
          tags: splitInputList(tagsInput),
          keywords: splitInputList(keywordsInput),
        }),
      })
      if (!response.ok) {
        throw new Error(await parseError(response))
      }
      const data = (await response.json()) as { document: ApiDocument }
      if (data.document) {
        setDocuments((prev) => prev.map((doc) => (doc.id === data.document.id ? data.document : doc)))
        setPreviewDoc(data.document)
        setResearchCard(metadataCard(data.document) ?? researchCard)
        setError(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存分类信息失败")
    } finally {
      setIsSavingMetadata(false)
    }
  }, [categoryInput, keywordsInput, previewDoc, researchCard, tagsInput])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      void uploadFiles(Array.from(e.dataTransfer.files))
    },
    [uploadFiles]
  )

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files || [])
      void uploadFiles(files)
      e.target.value = ""
    },
    [uploadFiles]
  )

  return (
    <div className="flex h-screen flex-col">
      <header className="shrink-0 border-b border-border bg-card/50 backdrop-blur-sm">
        <div className="px-4 py-4">
          <h1 className="text-lg font-semibold text-foreground">文献管理</h1>
          <p className="text-sm text-muted-foreground">上传、解析并管理知识库里的真实文档。</p>
        </div>
      </header>

      <div className="shrink-0 border-b border-border/50 bg-card/30 px-4 py-3">
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <div className="flex items-center gap-2">
            <FolderOpen className="h-4 w-4 text-primary" />
            <span className="text-muted-foreground">文档总数:</span>
            <span className="font-medium text-foreground">{stats.total}</span>
          </div>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-green-400" />
            <span className="text-muted-foreground">已解析:</span>
            <span className="font-medium text-foreground">{stats.parsed}</span>
          </div>
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" />
            <span className="text-muted-foreground">Chunks:</span>
            <span className="font-medium text-foreground">{stats.chunks}</span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto gap-2 text-xs"
            onClick={() => void loadDocuments()}
            disabled={isLoading}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isLoading && "animate-spin")} />
            刷新
          </Button>
        </div>
      </div>

      <div className="shrink-0 border-b border-border/50 px-4 py-3">
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索文档名称、作者或来源类型..."
              className="border-border/50 bg-secondary/50 pl-9"
            />
          </div>
          <select
            value={categoryFilter}
            onChange={(event) => setCategoryFilter(event.target.value)}
            className="h-10 w-36 rounded-md border border-border/50 bg-secondary/50 px-3 text-sm text-foreground outline-none focus:border-primary"
            aria-label="按分类筛选"
          >
            <option value="all">全部分类</option>
            {categoryOptions.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
          <label>
            <input
              type="file"
              accept=".pdf,.txt,.md,.docx"
              multiple
              onChange={handleFileInput}
              className="hidden"
              disabled={isUploading}
            />
            <Button asChild className="cursor-pointer gap-2" disabled={isUploading}>
              <span>
                <Upload className="h-4 w-4" />
                <span className="hidden sm:inline">{isUploading ? "上传中..." : "上传文献"}</span>
              </span>
            </Button>
          </label>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {error && (
          <div className="mb-4 flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-sm text-red-300">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <label
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={cn(
            "mb-4 block rounded-xl border-2 border-dashed p-6 text-center transition-all",
            isDragging ? "border-primary bg-primary/5" : "border-border/50 hover:border-border",
            isUploading ? "cursor-not-allowed opacity-70" : "cursor-pointer"
          )}
        >
          <input
            type="file"
            accept=".pdf,.txt,.md,.docx"
            multiple
            onChange={handleFileInput}
            className="hidden"
            disabled={isUploading}
          />
          <Upload
            className={cn(
              "mx-auto mb-2 h-8 w-8",
              isDragging ? "text-primary" : "text-muted-foreground"
            )}
          />
          <p className="text-sm text-muted-foreground">拖拽 PDF、TXT、Markdown 或 DOCX 到这里上传</p>
          <p className="mt-1 text-xs text-muted-foreground/60">
            上传后会自动入库，并尝试解析为可检索的 chunks
          </p>
        </label>

        <div className="space-y-3">
          {isLoading ? (
            <div className="py-12 text-center text-sm text-muted-foreground">正在加载文档列表...</div>
          ) : filteredDocuments.length === 0 ? (
            <div className="py-12 text-center">
              <FileText className="mx-auto h-12 w-12 text-muted-foreground/50" />
              <p className="mt-4 text-sm text-muted-foreground">
                {searchQuery ? "没有匹配的文档" : "还没有上传文档"}
              </p>
            </div>
          ) : (
            filteredDocuments.map((doc) => (
              <DocumentCard
                key={doc.id}
                document={doc}
                onDelete={handleDelete}
                onPreview={handlePreview}
                onAsk={(id) => onAskDocument?.(id)}
                deletingId={deletingId}
              />
            ))
          )}
        </div>
      </div>

      <Dialog
        open={!!previewDoc}
        onOpenChange={() => {
          setPreviewDoc(null)
          setPreviewChunks([])
          setResearchCard(null)
          setPreviewError(null)
          setResearchCardError(null)
        }}
      >
        <DialogContent className="max-h-[86vh] max-w-3xl overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              {previewDoc ? getDocumentDisplayName(previewDoc) : "文档详情"}
            </DialogTitle>
            <DialogDescription>查看后端真实存储的文档信息和解析状态。</DialogDescription>
          </DialogHeader>
          {previewDoc && (
            <div className="flex max-h-[calc(86vh-7rem)] flex-col gap-4 overflow-hidden">
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-2"
                  onClick={() => handleOpenDocumentFile(previewDoc)}
                >
                  <ExternalLink className="h-4 w-4" />
                  打开原文
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-2"
                  onClick={() => {
                    onAskDocument?.(previewDoc.id)
                    setPreviewDoc(null)
                  }}
                  disabled={previewDoc.status !== "parsed" || previewDoc.chunk_count <= 0}
                >
                  <MessageSquare className="h-4 w-4" />
                  问这篇
                </Button>
                <div className="ml-auto flex rounded-md border border-border/50 bg-secondary/40 p-1">
                  <Button
                    variant={previewMode === "card" ? "secondary" : "ghost"}
                    size="sm"
                    className="h-8 px-3 text-xs"
                    onClick={() => setPreviewMode("card")}
                  >
                    文献卡片
                  </Button>
                  <Button
                    variant={previewMode === "overview" ? "secondary" : "ghost"}
                    size="sm"
                    className="h-8 px-3 text-xs"
                    onClick={() => setPreviewMode("overview")}
                  >
                    基本信息
                  </Button>
                  <Button
                    variant={previewMode === "chunks" ? "secondary" : "ghost"}
                    size="sm"
                    className="h-8 px-3 text-xs"
                    onClick={() => setPreviewMode("chunks")}
                  >
                    解析片段
                  </Button>
                </div>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto pr-1">
              {previewMode === "card" ? (
                <div className="rounded-lg border border-border/50 bg-secondary/30 p-4">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-foreground">自动文献卡片</p>
                      <p className="text-xs text-muted-foreground">
                        自动整理这篇文献的主题、观点、结论和推荐分类。
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void handleGenerateResearchCard(!!researchCard)}
                      disabled={
                        isGeneratingResearchCard ||
                        isLoadingResearchCard ||
                        previewDoc.status !== "parsed" ||
                        previewDoc.chunk_count <= 0
                      }
                    >
                      {isGeneratingResearchCard ? "生成中..." : researchCard ? "重新生成" : "生成卡片"}
                    </Button>
                  </div>

                  {researchCardError && (
                    <div className="mb-3 rounded-md border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-300">
                      {researchCardError}
                    </div>
                  )}

                  {isLoadingResearchCard ? (
                    <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      正在读取文献卡片...
                    </div>
                  ) : !researchCard ? (
                    <div className="py-12 text-center text-sm text-muted-foreground">
                      这篇文献还没有生成卡片。
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div className="flex flex-wrap gap-2">
                        {cardText(researchCard, "suggested_category") && (
                          <Badge variant="outline" className="border-primary/20 bg-primary/10 text-primary">
                            {cardText(researchCard, "suggested_category")}
                          </Badge>
                        )}
                        {splitInputList(cardText(researchCard, "suggested_tags")).slice(0, 6).map((tag) => (
                          <Badge key={tag} variant="outline" className="text-muted-foreground">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                      <div className="grid gap-3">
                        {researchCardSections.map(([key, label]) => {
                          const value = cardText(researchCard, key)
                          if (!value) return null
                          return (
                            <div key={key} className="rounded-md border border-border/50 bg-background/40 p-3">
                              <p className="mb-1 text-xs font-medium text-muted-foreground">{label}</p>
                              <p className="max-h-28 overflow-y-auto whitespace-pre-wrap text-sm leading-6 text-foreground/90">
                                {value}
                              </p>
                            </div>
                          )
                        })}
                      </div>
                      {cardText(researchCard, "suggested_keywords") && (
                        <div className="rounded-md border border-border/50 bg-background/40 p-3">
                          <p className="mb-2 text-xs font-medium text-muted-foreground">建议关键词</p>
                          <div className="flex flex-wrap gap-2">
                            {splitInputList(cardText(researchCard, "suggested_keywords")).map((keyword) => (
                              <Badge key={keyword} variant="outline" className="text-muted-foreground">
                                {keyword}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : previewMode === "overview" ? (
                <>
              <div className="grid grid-cols-2 gap-4">
                <div className="rounded-lg bg-secondary/50 p-3">
                  <p className="text-xs text-muted-foreground">文件大小</p>
                  <p className="text-sm font-medium text-foreground">
                    {formatFileSize(previewDoc.file_size)}
                  </p>
                </div>
                <div className="rounded-lg bg-secondary/50 p-3">
                  <p className="text-xs text-muted-foreground">上传时间</p>
                  <p className="text-sm font-medium text-foreground">
                    {formatDate(previewDoc.created_at)}
                  </p>
                </div>
                <div className="rounded-lg bg-secondary/50 p-3">
                  <p className="text-xs text-muted-foreground">文件类型</p>
                  <p className="text-sm font-medium text-foreground">
                    {previewDoc.file_type || "-"}
                  </p>
                </div>
                <div className="rounded-lg bg-secondary/50 p-3">
                  <p className="text-xs text-muted-foreground">Chunks</p>
                  <p className="text-sm font-medium text-foreground">{previewDoc.chunk_count}</p>
                </div>
                <div className="rounded-lg bg-secondary/50 p-3">
                  <p className="text-xs text-muted-foreground">作者</p>
                  <p className="text-sm font-medium text-foreground">{previewDoc.author || "-"}</p>
                </div>
                <div className="rounded-lg bg-secondary/50 p-3">
                  <p className="text-xs text-muted-foreground">来源类型</p>
                  <p className="text-sm font-medium text-foreground">
                    {previewDoc.source_type || "-"}
                  </p>
                </div>
              </div>

              <div className="rounded-lg border border-border/50 bg-secondary/30 p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-foreground">分类与关键词</p>
                    <p className="text-xs text-muted-foreground">用逗号分隔多个标签或关键词</p>
                  </div>
                  <Button size="sm" variant="outline" onClick={handleSaveMetadata} disabled={isSavingMetadata}>
                    {isSavingMetadata ? "保存中..." : "保存"}
                  </Button>
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  <Input
                    value={categoryInput}
                    onChange={(event) => setCategoryInput(event.target.value)}
                    placeholder="主分类，如 岭南庭园"
                  />
                  <Input
                    value={tagsInput}
                    onChange={(event) => setTagsInput(event.target.value)}
                    placeholder="标签，如 夏昌世，莫伯治"
                  />
                  <Input
                    value={keywordsInput}
                    onChange={(event) => setKeywordsInput(event.target.value)}
                    placeholder="关键词，如 庭园理论，地域性"
                  />
                </div>
              </div>

              <div className="rounded-lg border border-border/50 bg-secondary/30 p-4">
                <p className="mb-2 text-xs text-muted-foreground">解析状态</p>
                <Badge
                  variant="outline"
                  className={cn("text-sm", statusConfig[previewDoc.status].className)}
                >
                  {(() => {
                    const StatusIcon = statusConfig[previewDoc.status].icon
                    return <StatusIcon className="mr-1 h-4 w-4" />
                  })()}
                  {statusConfig[previewDoc.status].label}
                </Badge>
                <p className="mt-3 text-xs text-muted-foreground">
                  文档 ID: {previewDoc.id}
                  {previewDoc.file_url ? ` / 文件地址: ${previewDoc.file_url}` : ""}
                </p>
              </div>
                </>
              ) : (
                <div className="rounded-lg border border-border/50 bg-secondary/30 p-4">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-foreground">解析片段预览</p>
                      <p className="text-xs text-muted-foreground">
                        显示前 12 个文本片段，用来检查文献是否被正确读入。
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void loadPreviewChunks(previewDoc)}
                      disabled={isLoadingPreviewChunks}
                    >
                      {isLoadingPreviewChunks ? "刷新中..." : "刷新"}
                    </Button>
                  </div>

                  {previewError && (
                    <div className="mb-3 rounded-md border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-300">
                      {previewError}
                    </div>
                  )}

                  {isLoadingPreviewChunks ? (
                    <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      正在读取解析片段...
                    </div>
                  ) : previewChunks.length === 0 ? (
                    <div className="py-12 text-center text-sm text-muted-foreground">
                      这篇文献还没有可查看的解析片段。
                    </div>
                  ) : (
                    <div className="max-h-[420px] space-y-3 overflow-y-auto pr-1">
                      {previewChunks.map((chunk) => (
                        <div key={chunk.id} className="rounded-md border border-border/50 bg-background/40 p-3">
                          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                            <Badge variant="outline" className="text-xs">
                              片段 {chunk.chunk_index + 1}
                            </Badge>
                            {chunk.section_title && <span>{chunk.section_title}</span>}
                            {chunk.page_start && (
                              <span>
                                页码 {chunk.page_start}
                                {chunk.page_end && chunk.page_end !== chunk.page_start ? `-${chunk.page_end}` : ""}
                              </span>
                            )}
                          </div>
                          <p className="whitespace-pre-wrap text-sm leading-6 text-foreground/90">
                            {chunk.content}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
