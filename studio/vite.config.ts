import { defineConfig } from 'vite'
import { tanstackStart } from '@tanstack/react-start/plugin/vite'
import react from '@vitejs/plugin-react'
import { nitro } from 'nitro/vite'

export default defineConfig({
  server: { host: '127.0.0.1', port: 4747, strictPort: true },
  plugins: [tanstackStart(), react(), nitro({ preset: 'node-server' })],
})
