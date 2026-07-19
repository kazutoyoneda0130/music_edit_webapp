import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 開発時はバックエンド(FastAPI, localhost:8000)へ同一オリジンとして見せかけることで、
      // セッションCookieまわりのCORS/SameSiteの問題を避ける。
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
