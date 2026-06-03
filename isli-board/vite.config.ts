import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'path'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      registerType: 'autoUpdate',
      includeAssets: ['favicon.png', 'apple-touch-icon.png', 'mask-icon.svg'],
      manifest: {
        name: 'ISLI Board',
        short_name: 'ISLI',
        description: 'ISLI Intelligent Kanban Board',
        theme_color: '#000000',
        background_color: '#000000',
        display: 'standalone',
        start_url: '/',
        orientation: 'portrait',
        icons: [
          {
            src: 'favicon.png',
            sizes: '64x64',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: 'pwa-192x192.png',
            sizes: '192x192',
            type: 'image/png'
          },
          {
            src: 'pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png'
          },
          {
            src: 'pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any maskable'
          }
        ],
        shortcuts: [
          {
            name: 'System Dashboard',
            short_name: 'Dashboard',
            description: 'View system node telemetry',
            url: '/',
            icons: [{ src: 'favicon.png', sizes: '64x64', type: 'image/png' }]
          },
          {
            name: 'Kanban Board',
            short_name: 'Kanban',
            description: 'Manage agent tasks',
            url: '/kanban',
            icons: [{ src: 'favicon.png', sizes: '64x64', type: 'image/png' }]
          }
        ]
      },
      workbox: {
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/api/'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: {
                maxEntries: 100,
                maxAgeSeconds: 60 * 60 * 24 * 7, // 1 week
              },
              cacheableResponse: {
                statuses: [0, 200],
              },
            },
          },
        ],
      },
    })
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.CORE_API_URL || 'http://isli-core:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/channels-api': {
        target: process.env.CHANNELS_API_URL || 'http://isli-channels:8200',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/channels-api/, ''),
      },
      '/ws': {
        target: process.env.CORE_API_URL || 'http://isli-core:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
