import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const API_TARGET = 'http://localhost:8000'

// Files in public/ that belong to the app shell.
const PUBLIC_SHELL = [
  '/',
  '/manifest.webmanifest',
  '/icon.svg',
  '/icon-192.png',
  '/icon-512.png',
  '/apple-touch-icon.png',
]

function hash(text: string): string {
  let h = 5381
  for (let i = 0; i < text.length; i++) h = ((h << 5) + h + text.charCodeAt(i)) >>> 0
  return h.toString(36)
}

/**
 * Emits sw.js at build time. It precaches the entry JS/CSS and the public
 * shell files, caches other hashed /assets/ files on first use, and never
 * touches /api, /s, /og or /story.
 */
function serviceWorker(): Plugin {
  return {
    name: 'cloudsea-service-worker',
    apply: 'build',
    enforce: 'post',
    generateBundle(_options, bundle) {
      const entry: string[] = []
      for (const [fileName, chunk] of Object.entries(bundle)) {
        if (chunk.type === 'chunk' && chunk.isEntry) {
          entry.push('/' + fileName)
          const css = (chunk as { viteMetadata?: { importedCss?: Set<string> } }).viteMetadata?.importedCss
          css?.forEach((f) => entry.push('/' + f))
        }
      }
      const shell = [...PUBLIC_SHELL, ...entry]
      const version = hash(Object.keys(bundle).sort().join('|'))
      const source = `// Generated at build time by vite.config.ts. App shell only.
const CACHE = 'cloudsea-${version}';
const SHELL = ${JSON.stringify(shell)};
const NEVER = /^\\/(api|s|og|story)(\\/|$)/;

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith('cloudsea-') && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || NEVER.test(url.pathname)) return;

  if (req.mode === 'navigate') {
    // Network first, so a new deploy shows up; the cached shell when offline.
    event.respondWith(fetch(req).catch(() => caches.match('/')));
    return;
  }
  if (url.pathname.startsWith('/assets/') || SHELL.includes(url.pathname)) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok && url.pathname.startsWith('/assets/')) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      }))
    );
  }
});
`
      this.emitFile({ type: 'asset', fileName: 'sw.js', source })
    },
  }
}

const proxy = {
  '/api': API_TARGET,
  // Regex keys, so "/s" doesn't also catch "/src/..." in dev.
  '^/s/': API_TARGET,
  '^/og/': API_TARGET,
  '^/story/': API_TARGET,
}

export default defineConfig({
  plugins: [react(), serviceWorker()],
  server: { proxy },
  preview: { proxy },
  build: {
    target: 'es2020',
  },
})
