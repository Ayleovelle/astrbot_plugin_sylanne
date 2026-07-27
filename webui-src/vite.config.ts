import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import { viteSingleFile } from 'vite-plugin-singlefile'
import { copyFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const sourceDir = dirname(fileURLToPath(import.meta.url))

function astrBotPluginPage(): Plugin {
  return {
    name: 'sylanne-astrbot-plugin-page',
    transformIndexHtml: {
      order: 'post',
      handler(html): string {
        return html.replace(/\r\n?/g, '\n')
      },
    },
    closeBundle(): void {
      const builtPage = resolve(sourceDir, '../UI/index.html')
      const nativePage = resolve(sourceDir, '../pages/dashboard/index.html')
      mkdirSync(dirname(nativePage), { recursive: true })
      copyFileSync(builtPage, nativePage)
    },
  }
}

// The AstrBot plugin ships via git (no build step at install time) and its two
// existing HTTP backends already read + serve one file: UI/index.html. So we
// build the whole Vue app into a single self-contained UI/index.html — zero
// backend change, honoring the "只修红线不动后端架构" constraint. The committed
// UI/index.html IS the build artifact; source lives here in webui-src/.
export default defineConfig({
  plugins: [vue(), viteSingleFile(), astrBotPluginPage()],
  base: './',
  // Dev-only: proxy API/WebSocket to a running plugin WebUI (default port 2718)
  // so `pnpm dev` shows live data. If no backend is up, the client falls back to
  // a dev mock. Neither affects the production single-file build.
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:2718', changeOrigin: true },
      '/ws': { target: 'http://127.0.0.1:2718', changeOrigin: true, ws: true },
    },
  },
  build: {
    outDir: '../UI',
    emptyOutDir: false, // never wipe UI/ (keeps UI/assets and siblings)
    cssCodeSplit: false,
    assetsInlineLimit: 100_000_000,
    chunkSizeWarningLimit: 8000,
  },
})
