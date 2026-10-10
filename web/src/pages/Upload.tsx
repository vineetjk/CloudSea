import { useEffect, useRef, useState } from 'react'
import { API_BASE, ApiError, MOCK, confirmPhoto, getPhoto, uploadPhoto } from '../api'
import { PHOTO_LABELS, PHOTO_LABEL_ORDER, shortDate } from '../format'
import { formatIstIso, istParts } from '../lib/dates'
import { UnreadableImageError, loadExifr, readExif, resizeToJpeg } from '../lib/image'
import { PhotoTooLargeError, checkPhoto, type PhotoCheck } from '../lib/photoRules'
import { KEYS, readJson, writeJson, type StoredPhoto } from '../storage'
import type { Photo, PhotoLabel } from '../types'

const POLL_MS = 15_000

const LABEL_HINTS: Record<PhotoLabel, string> = {
  cloud_sea: 'A layer of cloud below you, filling the valleys.',
  partial: 'Some cloud below, with gaps or patches.',
  clear_no_sea: 'You can see the ground below. No cloud layer.',
  socked_in: "You're in the cloud. Little or no view.",
}

interface Ready {
  blob: Blob
  url: string
  width: number
  height: number
  check: Extract<PhotoCheck, { ok: true }>
}

type Stage =
  | { kind: 'idle' }
  | { kind: 'checking' }
  | { kind: 'rejected'; message: string }
  | ({ kind: 'ready' | 'uploading' } & Ready)
  | ({ kind: 'failed'; error: string } & Ready)
  | { kind: 'uploaded'; id: string; token: string; url: string; isPublic: boolean }

const kb = (bytes: number) => `${Math.round(bytes / 1024)} KB`

export default function Upload() {
  const [stage, setStage] = useState<Stage>({ kind: 'idle' })
  const [isPublic, setPublic] = useState(false)
  const [demoSkipChecks, setDemoSkipChecks] = useState(false)
  const [mine, setMine] = useState<StoredPhoto[]>(() => readJson<StoredPhoto[]>(KEYS.photos, []))
  const input = useRef<HTMLInputElement>(null)
  const previewUrl = 'url' in stage ? stage.url : null

  // Fetch exifr while the person finds their photo.
  useEffect(() => {
    loadExifr().catch(() => undefined)
  }, [])

  // Free the preview image when it's replaced or the page closes.
  useEffect(() => {
    if (!previewUrl) return
    return () => URL.revokeObjectURL(previewUrl)
  }, [previewUrl])

  async function onPick(file: File | undefined) {
    if (!file) return
    setStage({ kind: 'checking' })
    let check: PhotoCheck
    try {
      const exif = await readExif(file)
      check = checkPhoto(exif, Date.now())
      if (MOCK && demoSkipChecks && !check.ok) {
        check = { ok: true, takenAt: formatIstIso(Date.now()), gpsPresent: false, distanceKm: null }
      }
    } catch {
      setStage({ kind: 'rejected', message: "We couldn't load the photo checker. Check your connection and try again." })
      return
    }
    if (!check.ok) {
      setStage({ kind: 'rejected', message: check.message })
      return
    }
    try {
      const r = await resizeToJpeg(file)
      setStage({ kind: 'ready', blob: r.blob, url: URL.createObjectURL(r.blob), width: r.width, height: r.height, check })
    } catch (e) {
      const message =
        e instanceof PhotoTooLargeError || e instanceof UnreadableImageError
          ? e.message
          : "This browser couldn't open that image. Please try a JPEG photo."
      setStage({ kind: 'rejected', message })
    }
  }

  async function onUpload() {
    if (stage.kind !== 'ready' && stage.kind !== 'failed') return
    const ready: Ready = { blob: stage.blob, url: stage.url, width: stage.width, height: stage.height, check: stage.check }
    setStage({ kind: 'uploading', ...ready })
    try {
      const res = await uploadPhoto({
        photo: ready.blob,
        takenAt: ready.check.takenAt,
        gpsPresent: ready.check.gpsPresent,
        distanceKm: ready.check.distanceKm,
        isPublic,
      })
      const entry: StoredPhoto = { id: res.id, token: res.token, date: istParts(Date.now()).date }
      const next = [entry, ...mine.filter((p) => p.id !== res.id)].slice(0, 10)
      writeJson(KEYS.photos, next)
      setMine(next)
      setStage({ kind: 'uploaded', id: res.id, token: res.token, url: ready.url, isPublic })
    } catch (e) {
      setStage({
        kind: 'failed',
        ...ready,
        error: e instanceof ApiError ? e.message : 'The upload failed. Please try again.',
      })
    }
  }

  function reset() {
    setStage({ kind: 'idle' })
    if (input.current) input.current.value = ''
  }

  const earlier = mine.filter((p) => !(stage.kind === 'uploaded' && p.id === stage.id)).slice(0, 3)

  return (
    <div className="stack">
      <div className="page-head">
        <h1>At the top? Add your sunrise photo</h1>
        <p className="lede">
          One photo from the Nandi Hills summit, taken today between 5:00 and 8:30 AM. Gemma 4 rates what it shows, you
          confirm with one tap, and your answer becomes part of this morning's grade.
        </p>
      </div>

      {stage.kind === 'uploaded' ? (
        <section className="card" aria-labelledby="status-h">
          <h2 id="status-h" className="card-title">
            Your photo
          </h2>
          <PhotoStatus id={stage.id} token={stage.token} preview={stage.url} initialPublic={stage.isPublic} />
          <button type="button" className="btn" onClick={reset}>
            Add another photo
          </button>
        </section>
      ) : (
        <section className="card" aria-labelledby="pick-h">
          <h2 id="pick-h" className="card-title">
            Your sunrise photo
          </h2>
          <label className="btn btn-primary file-btn">
            {stage.kind === 'idle' || stage.kind === 'checking' ? 'Choose a photo' : 'Choose a different photo'}
            <input
              ref={input}
              className="sr-only"
              type="file"
              accept="image/*"
              onChange={(e) => onPick(e.target.files?.[0])}
            />
          </label>
          <p className="muted small">
            Pick the original from your camera or gallery. We check the time it was taken, and the place if your phone
            saved it, before anything is uploaded.
          </p>
          {MOCK && (
            <label className="check demo-only">
              <input type="checkbox" checked={demoSkipChecks} onChange={(e) => setDemoSkipChecks(e.target.checked)} />
              <span>Demo only: skip the time and place checks</span>
            </label>
          )}

          {stage.kind === 'checking' && (
            <p role="status" className="loading">
              <span className="spinner" aria-hidden="true" /> Checking the photo…
            </p>
          )}
          {stage.kind === 'rejected' && (
            <div className="notice notice-warn" role="alert">
              <p>{stage.message}</p>
            </div>
          )}

          {(stage.kind === 'ready' || stage.kind === 'uploading' || stage.kind === 'failed') && (
            <div className="ready">
              <img className="preview" src={stage.url} alt="Your photo, resized for upload" width={stage.width} height={stage.height} />
              <p className="muted small">
                Taken at {stage.check.takenAt.slice(11, 16)} · {stage.width} × {stage.height} px · {kb(stage.blob.size)}
                {stage.check.distanceKm !== null && <> · {stage.check.distanceKm.toFixed(1)} km from the summit</>}
              </p>
              <p className="privacy">
                Photos are private unless you choose to share them in the public gallery. We remove all location and
                camera data before storing.
              </p>
              <label className="switch">
                <input type="checkbox" role="switch" checked={isPublic} onChange={(e) => setPublic(e.target.checked)} />
                <span>Add to public gallery</span>
              </label>
              <button type="button" className="btn btn-primary" onClick={onUpload} disabled={stage.kind === 'uploading'}>
                {stage.kind === 'uploading' ? 'Uploading…' : 'Upload photo'}
              </button>
              {stage.kind === 'failed' && (
                <div className="notice notice-error" role="alert">
                  <p>{stage.error}</p>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {earlier.length > 0 && (
        <section className="card" aria-labelledby="earlier-h">
          <h2 id="earlier-h" className="card-title">
            Your recent photos
          </h2>
          <ul className="photo-list">
            {earlier.map((p) => (
              <li key={p.id}>
                <PhotoStatus
                  id={p.id}
                  token={p.token}
                  preview={MOCK ? null : `${API_BASE}/api/photos/${encodeURIComponent(p.id)}/image?token=${encodeURIComponent(p.token)}`}
                  compact
                />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function PhotoStatus({
  id,
  token,
  preview,
  initialPublic,
  compact = false,
}: {
  id: string
  token: string
  preview: string | null
  initialPublic?: boolean
  compact?: boolean
}) {
  const [photo, setPhoto] = useState<Photo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [gone, setGone] = useState(false)
  const [pub, setPub] = useState<boolean | null>(initialPublic ?? null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let live = true
    let timer: ReturnType<typeof setTimeout> | undefined
    async function tick() {
      try {
        const p = await getPhoto(id, token)
        if (!live) return
        setPhoto(p)
        setError(null)
        if (p.status === 'queued') timer = setTimeout(tick, POLL_MS)
      } catch (e) {
        if (!live) return
        if (e instanceof ApiError && (e.status === 404 || e.status === 403)) {
          setGone(true)
          return
        }
        setError("We couldn't check on your photo. Trying again in 15 seconds.")
        timer = setTimeout(tick, POLL_MS)
      }
    }
    tick()
    return () => {
      live = false
      clearTimeout(timer)
    }
  }, [id, token])

  async function confirm(label: PhotoLabel) {
    setBusy(true)
    setError(null)
    try {
      setPhoto(await confirmPhoto(id, token, label, pub ?? photo?.public ?? false))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That didn't save. Please try again.")
    } finally {
      setBusy(false)
    }
  }

  if (gone) return <p className="muted">This photo is no longer available.</p>

  const isPublic = pub ?? photo?.public ?? false
  const img = preview && (
    <img className={compact ? 'thumb' : 'preview'} src={preview} alt="Your sunrise photo" loading="lazy" />
  )

  return (
    <div className={compact ? 'photo-status compact' : 'photo-status'}>
      {img}
      <div aria-live="polite">
        {!photo && !error && <p className="muted">Checking on your photo…</p>}

        {photo?.status === 'queued' && (
          <p className="loading">
            <span className="spinner" aria-hidden="true" />
            <span>
              Uploaded. Gemma is looking at your photo; this usually takes a few minutes. You can leave this page and
              come back.
            </span>
          </p>
        )}

        {photo?.status === 'rated' && photo.confirmed_label && (
          <p>
            <span aria-hidden="true">✓ </span>
            Thanks. You confirmed <strong>{PHOTO_LABELS[photo.confirmed_label]}</strong>. It counts toward the grade
            for {photo.date ? shortDate(photo.date) : 'that morning'}.{' '}
            {photo.public ? 'It will appear in the public gallery.' : 'It stays private.'}
          </p>
        )}

        {photo?.status === 'rated' && !photo.confirmed_label && photo.rating && (
          <div className="rating">
            <p>
              Gemma's read: <strong>{PHOTO_LABELS[photo.rating.label]}</strong>
            </p>
            <blockquote className="evidence-quote">{photo.rating.evidence}</blockquote>
            <p className="ask">Is that right?</p>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => confirm(photo.rating!.label)}>
              Yes, that's right
            </button>
            <p className="muted small">Or choose what you saw:</p>
            <div className="label-choices">
              {PHOTO_LABEL_ORDER.filter((l) => l !== photo.rating!.label).map((l) => (
                <button key={l} type="button" className="btn choice" disabled={busy} onClick={() => confirm(l)}>
                  <span className="choice-name">{PHOTO_LABELS[l]}</span>
                  <span className="choice-hint">{LABEL_HINTS[l]}</span>
                </button>
              ))}
            </div>
            <label className="switch">
              <input type="checkbox" role="switch" checked={isPublic} onChange={(e) => setPub(e.target.checked)} />
              <span>Add to public gallery</span>
            </label>
          </div>
        )}

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </div>
    </div>
  )
}
