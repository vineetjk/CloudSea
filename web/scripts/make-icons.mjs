// Draws the CloudSea icon (a sun rising over a cloud layer) and writes
// public/icon.svg plus PNG icons. No dependencies: a tiny rasteriser with
// 4x4 supersampling and a PNG encoder on top of node:zlib.
// Run with `npm run icons`.
import { writeFileSync } from 'node:fs'
import { deflateSync } from 'node:zlib'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const out = join(dirname(fileURLToPath(import.meta.url)), '..', 'public')

// Scene in unit coordinates (0..1, y down).
const SKY = [
  [0.0, [0x14, 0x1a, 0x45]],
  [0.45, [0x3b, 0x33, 0x78]],
  [0.68, [0xf0, 0x95, 0x5a]],
]
const SUN = { cx: 0.5, cy: 0.6, r: 0.19, color: [0xf7, 0xc9, 0x5c] }
const CLOUD_TOP = [0xf6, 0xf3, 0xfb]
const CLOUD_LOW = [0xd9, 0xd5, 0xef]
const BUMPS = [
  [0.06, 0.71, 0.12],
  [0.27, 0.655, 0.125],
  [0.5, 0.695, 0.115],
  [0.73, 0.645, 0.13],
  [0.95, 0.7, 0.12],
]
const CLOUD_BASE = 0.69

const mix = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t)

function sky(y) {
  if (y <= SKY[0][0]) return SKY[0][1]
  for (let i = 1; i < SKY.length; i++) {
    if (y <= SKY[i][0]) {
      const [y0, c0] = SKY[i - 1]
      const [y1, c1] = SKY[i]
      return mix(c0, c1, (y - y0) / (y1 - y0))
    }
  }
  return SKY[SKY.length - 1][1]
}

function inCloud(x, y) {
  if (y >= CLOUD_BASE) return true
  return BUMPS.some(([cx, cy, r]) => (x - cx) ** 2 + (y - cy) ** 2 <= r * r)
}

// Colour at a point in the full-bleed scene.
function scene(x, y) {
  if (inCloud(x, y)) return mix(CLOUD_TOP, CLOUD_LOW, Math.min(1, Math.max(0, (y - 0.62) / 0.38)))
  const d = Math.hypot(x - SUN.cx, y - SUN.cy)
  if (d <= SUN.r) return SUN.color
  const glow = Math.max(0, 1 - (d - SUN.r) / 0.12) * 0.35
  return mix(sky(y), SUN.color, glow)
}

// rounded: corner radius as a fraction of the size (0 = full bleed).
function render(size, rounded) {
  const S = 4
  const px = Buffer.alloc(size * size * 4)
  const rad = rounded * size
  for (let j = 0; j < size; j++) {
    for (let i = 0; i < size; i++) {
      let r = 0, g = 0, b = 0, a = 0
      for (let sj = 0; sj < S; sj++) {
        for (let si = 0; si < S; si++) {
          const fx = i + (si + 0.5) / S
          const fy = j + (sj + 0.5) / S
          if (rad > 0) {
            const qx = Math.max(rad - fx, fx - (size - rad), 0)
            const qy = Math.max(rad - fy, fy - (size - rad), 0)
            if (qx * qx + qy * qy > rad * rad) continue
          }
          const c = scene(fx / size, fy / size)
          r += c[0]; g += c[1]; b += c[2]; a += 1
        }
      }
      const o = (j * size + i) * 4
      const n = S * S
      if (a > 0) {
        px[o] = Math.round(r / a)
        px[o + 1] = Math.round(g / a)
        px[o + 2] = Math.round(b / a)
      }
      px[o + 3] = Math.round((a / n) * 255)
    }
  }
  return px
}

const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
  return c >>> 0
})
function crc32(buf) {
  let c = 0xffffffff
  for (const byte of buf) c = CRC_TABLE[(c ^ byte) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}
function chunk(type, data) {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const td = Buffer.concat([Buffer.from(type, 'ascii'), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(td))
  return Buffer.concat([len, td, crc])
}
function png(size, rgba) {
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(size, 0)
  ihdr.writeUInt32BE(size, 4)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 6 // RGBA
  const raw = Buffer.alloc(size * (size * 4 + 1))
  for (let y = 0; y < size; y++) {
    raw[y * (size * 4 + 1)] = 0 // filter: none
    rgba.copy(raw, y * (size * 4 + 1) + 1, y * size * 4, (y + 1) * size * 4)
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

const hex = (c) => '#' + c.map((v) => Math.round(v).toString(16).padStart(2, '0')).join('')
const n = (v) => +(v * 512).toFixed(1)

function svg() {
  const stops = SKY.map(([o, c]) => `<stop offset="${o}" stop-color="${hex(c)}"/>`).join('')
  const bumps = BUMPS.map(([cx, cy, r]) => `<circle cx="${n(cx)}" cy="${n(cy)}" r="${n(r)}"/>`).join('')
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<defs>
<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">${stops}</linearGradient>
<linearGradient id="cloud" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${hex(CLOUD_TOP)}"/><stop offset="1" stop-color="${hex(CLOUD_LOW)}"/></linearGradient>
<radialGradient id="glow"><stop offset="0.6" stop-color="${hex(SUN.color)}" stop-opacity="0.35"/><stop offset="1" stop-color="${hex(SUN.color)}" stop-opacity="0"/></radialGradient>
<clipPath id="r"><rect width="512" height="512" rx="${n(0.2)}"/></clipPath>
</defs>
<g clip-path="url(#r)">
<rect width="512" height="512" fill="url(#sky)"/>
<circle cx="${n(SUN.cx)}" cy="${n(SUN.cy)}" r="${n(SUN.r + 0.12)}" fill="url(#glow)"/>
<circle cx="${n(SUN.cx)}" cy="${n(SUN.cy)}" r="${n(SUN.r)}" fill="${hex(SUN.color)}"/>
<g fill="url(#cloud)">${bumps}<rect x="0" y="${n(CLOUD_BASE)}" width="512" height="${n(1 - CLOUD_BASE)}"/></g>
</g>
</svg>
`
}

writeFileSync(join(out, 'icon.svg'), svg())
const icons = [
  ['icon-192.png', 192, 0.2],
  ['icon-512.png', 512, 0.2],
  ['icon-maskable-512.png', 512, 0], // full bleed; the sun sits inside the safe zone
  ['apple-touch-icon.png', 180, 0], // iOS rounds the corners itself
]
for (const [name, size, rounded] of icons) {
  writeFileSync(join(out, name), png(size, render(size, rounded)))
  console.log('wrote', name)
}
console.log('wrote icon.svg')
