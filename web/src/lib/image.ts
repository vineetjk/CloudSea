// Browser-only photo helpers: read EXIF, then decode and re-encode with a
// canvas. Canvas output carries no EXIF. The size rules live in photoRules.ts.

import { encodeUnderLimit, fitWithin } from './photoRules'

let exifrPromise: Promise<typeof import('exifr/dist/lite.esm.mjs').default> | null = null

/** Starts downloading exifr (lite build) without waiting for it. */
export function loadExifr() {
  exifrPromise ??= import('exifr/dist/lite.esm.mjs').then((m) => m.default)
  return exifrPromise
}

/** Raw EXIF strings and GPS, read before any resizing. Undefined if none. */
export async function readExif(file: File): Promise<Record<string, unknown> | undefined> {
  const exifr = await loadExifr()
  try {
    return await exifr.parse(file, {
      ifd0: false,
      ifd1: false,
      interop: false,
      xmp: false,
      icc: false,
      iptc: false,
      jfif: false,
      exif: ['DateTimeOriginal', 'OffsetTimeOriginal'],
      gps: ['GPSLatitude', 'GPSLatitudeRef', 'GPSLongitude', 'GPSLongitudeRef'],
      // Keep the date as the raw string; we convert it to IST ourselves.
      reviveValues: false,
      translateValues: false,
      mergeOutput: true,
    })
  } catch {
    return undefined
  }
}

interface Decoded {
  source: CanvasImageSource
  width: number
  height: number
  release: () => void
}

async function decode(file: File): Promise<Decoded> {
  if (typeof createImageBitmap === 'function') {
    try {
      const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' })
      return { source: bmp, width: bmp.width, height: bmp.height, release: () => bmp.close() }
    } catch {
      /* fall back to an <img> */
    }
  }
  const url = URL.createObjectURL(file)
  const img = new Image()
  img.src = url
  try {
    await img.decode()
  } catch {
    URL.revokeObjectURL(url)
    throw new UnreadableImageError()
  }
  return { source: img, width: img.naturalWidth, height: img.naturalHeight, release: () => URL.revokeObjectURL(url) }
}

export class UnreadableImageError extends Error {
  constructor() {
    super("This browser couldn't open that image. Please try a JPEG photo, or set your camera to its most compatible format.")
  }
}

function toJpeg(canvas: HTMLCanvasElement, quality: number): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new UnreadableImageError())), 'image/jpeg', quality),
  )
}

export interface Resized {
  blob: Blob
  width: number
  height: number
  quality: number
}

/** At most 1280 px on the long edge, JPEG, at most 200 KB. */
export async function resizeToJpeg(file: File): Promise<Resized> {
  const img = await decode(file)
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    img.release()
    throw new UnreadableImageError()
  }
  let drawnEdge = 0
  try {
    const { output, quality } = await encodeUnderLimit(async (q, maxEdge) => {
      if (maxEdge !== drawnEdge) {
        const { width, height } = fitWithin(img.width, img.height, maxEdge)
        canvas.width = width
        canvas.height = height
        ctx.fillStyle = '#ffffff'
        ctx.fillRect(0, 0, width, height)
        ctx.imageSmoothingEnabled = true
        ctx.imageSmoothingQuality = 'high'
        ctx.drawImage(img.source, 0, 0, width, height)
        drawnEdge = maxEdge
      }
      return toJpeg(canvas, q)
    })
    return { blob: output, width: canvas.width, height: canvas.height, quality }
  } finally {
    img.release()
  }
}
