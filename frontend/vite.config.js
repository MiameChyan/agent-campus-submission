import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发时把 /api 代理到 FastAPI（uvicorn src.server:app --port 8000）
export default defineConfig({
  plugins: [vue()],
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8000' } },
})
