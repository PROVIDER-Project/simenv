import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // three.js + three-globe legitimately exceed the 500 kB default; split them
    // into their own long-cached vendor chunk rather than bloating the app chunk,
    // and raise the warning threshold to cover that (unavoidable) 3D vendor size.
    chunkSizeWarningLimit: 2000,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (/[\\/](three|three-globe)[\\/]/.test(id)) return 'three-vendor'
          if (/[\\/](globe\.gl|react-globe\.gl)[\\/]/.test(id)) return 'globe-vendor'
          return undefined
        },
      },
    },
  },
})
