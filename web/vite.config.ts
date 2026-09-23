import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Dev-only proxy: the Agent API becomes same-origin from the browser's point of view.
    //
    // Why a proxy instead of CORSMiddleware on FastAPI: the browser then talks only to :5173, so
    // there is no cross-origin request to permit. The alternative -- `allow_origins` in the Agent
    // API -- puts a permissive wildcard in the *production* configuration of a service that accepts
    // Bearer credentials, and "we'll tighten it later" is how that becomes an incident. A proxy makes
    // the unsafe configuration impossible instead of discouraged, at the cost of one file.
    //
    // This exists only in `npm run dev`. A production build does not proxy: it must be served from
    // the same origin as the API (T081's compose topology) or configured deliberately.
    proxy: {
      // The Agent API is mounted at /api/v1 (the contract's server URL), while the page talks to
      // /agent/... . Rewriting here keeps one prefix in the UI and one in the service, instead of
      // making either side carry the other's convention.
      //
      // This mismatch was found by running the chain: /health proxied fine (no rewrite needed) while
      // every /agent/runs call came back 404 from FastAPI -- a 404 that looks like "route missing"
      // rather than "proxy path wrong", which is exactly why the check is end-to-end.
      '/agent': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/agent/, '/api/v1/agent'),
      },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: false },
      // T024 page-level acceptance: call the Java business authority directly from :5173.
      // This is intentionally a Java API validation path, not the final Agent Tool path.
      '/commerce': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/commerce/, '/api/v1'),
      },
    },
  },
})
