import { dirname } from "node:path"
import { fileURLToPath } from "node:url"

const appDir = dirname(fileURLToPath(import.meta.url))
const outputMode = process.env.NEXT_OUTPUT_MODE === "export" ? "export" : "standalone"

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: outputMode,
  turbopack: {
    root: appDir,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
}

export default nextConfig
