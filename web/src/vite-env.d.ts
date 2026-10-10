/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the CloudSea API, e.g. "https://api.example.org". Default "" (same origin). */
  readonly VITE_API_BASE?: string
  /** "1" to use the demo fixtures in src/mocks instead of the API. */
  readonly VITE_MOCK?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module 'exifr/dist/lite.esm.mjs' {
  const exifr: {
    parse(input: Blob | ArrayBuffer, options?: Record<string, unknown>): Promise<Record<string, unknown> | undefined>
  }
  export default exifr
}
