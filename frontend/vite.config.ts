import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { sentryVitePlugin } from '@sentry/vite-plugin'
import { visualizer } from 'rollup-plugin-visualizer'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const productionBuild = mode === 'production'
  const sentryUploadConfigured =
    productionBuild &&
    Boolean(process.env.SENTRY_AUTH_TOKEN) &&
    Boolean(process.env.SENTRY_ORG) &&
    Boolean(process.env.SENTRY_PROJECT)

  return {
    plugins: [
      react(),
      tailwindcss(),
      sentryUploadConfigured
        ? sentryVitePlugin({
            authToken: process.env.SENTRY_AUTH_TOKEN,
            org: process.env.SENTRY_ORG,
            project: process.env.SENTRY_PROJECT,
            release: {
              name: process.env.VITE_APP_RELEASE || 'unknown',
            },
            sourcemaps: {
              filesToDeleteAfterUpload: ['dist/**/*.map'],
            },
          })
        : undefined,
      process.env.BUNDLE_ANALYZE === '1'
        ? visualizer({
            filename: 'dist/stats.html',
            gzipSize: true,
            brotliSize: true,
            open: false,
          })
        : undefined,
    ].filter(Boolean),
    base: "/",
    build: {
      sourcemap: sentryUploadConfigured ? 'hidden' : false,
    },
    resolve: {
      tsconfigPaths: true,
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      proxy: {
        '/api': 'http://127.0.0.1:8000',
        '/static': 'http://127.0.0.1:8000',
      },
    },
  }
})
