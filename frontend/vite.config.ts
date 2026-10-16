import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 图表库 @ant-design/charts（含 @antv/g2 全家桶）压缩后约 1.4MB，且**只有驾驶舱页面**用到。
// 处理策略（2026-10-16 三组对照实验后确定）：
//   1. 用 manualChunks 把图表库单独拆成一个 chunk —— 页面 chunk 从 1.4MB 降到 10KB 级，
//      图表库成为可长期缓存的独立文件（改业务代码不必重下）。
//   2. 必须在 modulePreload.resolveDependencies 里把它排除掉：
//      实测 rolldown 会把手工拆出的 chunk 一并写进入口 modulepreload，
//      导致登录页被迫下载 1.4MB。排除后首屏只预加载 react-dom / jsx-runtime / spin。
//   3. 不要改用「Dashboard 内动态 import」来拆：动态 chunk 无法与入口块共享模块，
//      图表块会从 1.4MB 膨胀到 2.2MB（实测）。
//   4. 不要手工聚合 antd / react 成 vendor：会破坏打包器对 antd 的按组件细粒度切分，
//      反而把首屏块做大（实测 vendor 被撑到 1.79MB 并被预加载）。
const CHARTS_CHUNK = 'vendor-charts'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8003',
        changeOrigin: true
      }
    }
  },
  build: {
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (
            id.includes('node_modules') &&
            (id.includes('@ant-design/charts') || id.includes('@antv'))
          ) {
            return CHARTS_CHUNK
          }
          return undefined
        }
      }
    },
    modulePreload: {
      // 图表库按需加载，不参与首屏预加载
      resolveDependencies(_filename: string, deps: string[]) {
        return deps.filter((dep) => !dep.includes(CHARTS_CHUNK))
      }
    }
  }
})
