/**
 * 统一的 API 请求封装。
 *
 * 背景：后端异常时（比如 Hugging Face Space 崩溃，返回 503 的 HTML 页面），
 * 直接 `res.json()` 会抛出 `Unexpected token 'Y', "Your space"... is not valid JSON`
 * 这种完全看不懂的报错，用户根本不知道发生了什么。
 *
 * 这里的做法是：先读文本，再尝试解析 JSON，解析失败也不抛异常；
 * 非 2xx 一律抛 ApiError，message 是可以直接展示给用户的中文说明。
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"

export class ApiError extends Error {
  status: number
  detail?: unknown

  constructor(message: string, status: number, detail?: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }
}

/** 把 HTML 片段压成一行纯文本，用于兜底展示。 */
function toPlainText(value: string): string {
  return value
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}

function messageForStatus(status: number): string {
  if (status === 502 || status === 503 || status === 504) {
    return `后端服务暂时不可用（${status}），服务可能正在启动或被暂停，请稍后重试`
  }
  if (status === 404) {
    return "请求的接口不存在（404），可能是前后端版本不一致"
  }
  if (status === 401 || status === 403) {
    return `没有访问权限（${status}）`
  }
  if (status >= 500) {
    return `后端出错了（${status}），请稍后重试`
  }
  return `请求失败（${status}）`
}

/** 从响应体里挑出后端主动给出的说明（detail / error / message）。 */
function appMessageFrom(data: unknown): string | undefined {
  if (!data || typeof data !== "object") return undefined
  const body = data as Record<string, unknown>
  return [body.detail, body.error, body.message].find(
    (item): item is string => typeof item === "string" && item.trim().length > 0
  )
}

/**
 * 由状态码和响应体生成给人看的错误说明。
 * 后端自己的说明优先，其次按状态码给通用提示，最后才用响应文本兜底。
 */
export function describeHttpError(
  status: number,
  data: unknown,
  text = ""
): string {
  const appMessage = appMessageFrom(data)
  if (appMessage) return appMessage

  const friendly = messageForStatus(status)
  if (friendly) return friendly

  const plain = toPlainText(text).slice(0, 160)
  return plain || `请求失败（${status}）`
}

/** 读取响应体：优先按 JSON 解析，失败则退化成纯文本，绝不因为解析失败而抛异常。 */
export async function readBody(
  res: Response
): Promise<{ data: unknown; text: string }> {
  const text = await res.text()
  if (!text) return { data: null, text: "" }
  try {
    return { data: JSON.parse(text), text }
  } catch {
    return { data: null, text }
  }
}

/** 把一个非 2xx 响应转成可直接展示的错误说明。 */
export async function parseErrorResponse(res: Response): Promise<string> {
  const { data, text } = await readBody(res)
  return describeHttpError(res.status, data, text)
}

/**
 * 发起请求并返回解析后的数据。
 * 非 2xx 一律抛 ApiError，`message` 可直接展示给用户。
 */
export async function apiRequest<T = any>(
  url: string,
  init?: RequestInit
): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, init)
  } catch {
    // 只有真正连不上才会走到这里：DNS 失败、连接被拒、CORS 被拦
    throw new ApiError("连不上后端服务，请检查网络后重试", 0)
  }

  const { data, text } = await readBody(res)

  if (!res.ok) {
    throw new ApiError(describeHttpError(res.status, data, text), res.status)
  }

  if (data === null && text.trim()) {
    // 200 但不是 JSON，通常是网关或反向代理返回了 HTML
    throw new ApiError("后端返回了非预期的内容，请稍后重试", res.status)
  }

  return data as T
}

/** 从任意异常里取出可以直接展示的中文说明。 */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) {
    // 浏览器在网络层失败时只会给出 "Failed to fetch" 这类英文短语，
    // 直接显示给用户没有任何意义，这里统一换成人话。
    if (/failed to fetch|networkerror|load failed|network request failed/i.test(err.message)) {
      return "连不上后端服务，请检查网络后重试"
    }
    return err.message
  }
  return "请求失败，请稍后重试"
}

/** 同上，但允许在无法识别时使用调用方自己的兜底文案。 */
export function describeError(err: unknown, fallback: string): string {
  const message = errorMessage(err)
  return message === "请求失败，请稍后重试" ? fallback : message
}
