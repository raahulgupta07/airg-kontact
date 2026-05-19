<script>
  import { goto } from '$app/navigation';
  import { onMount, onDestroy } from 'svelte';
  import exifr from 'exifr';
  import { uploadQueue } from '$lib/uploadQueue.svelte';

  async function readClientExif(file) {
    try {
      const meta = await exifr.parse(file, {
        gps: true, exif: true, xmp: true, iptc: true,
        ifd0: true, makerNote: false, userComment: false
      });
      if (!meta) return null;
      return {
        filename: file.name,
        gps_lat: meta.latitude,
        gps_lng: meta.longitude,
        gps_altitude: meta.GPSAltitude,
        gps_heading: meta.GPSImgDirection,
        gps_speed: meta.GPSSpeed,
        date_taken: meta.DateTimeOriginal ? new Date(meta.DateTimeOriginal).toISOString() : null,
        camera_make: meta.Make,
        camera_model: meta.Model,
        lens_model: meta.LensModel || meta.LensInfo,
        focal_length: meta.FocalLength,
        f_number: meta.FNumber,
        iso: meta.ISO || meta.ISOSpeedRatings,
        exposure_time: meta.ExposureTime,
        software: meta.Software,
        orientation: meta.Orientation,
        img_width: meta.ImageWidth || meta.ExifImageWidth,
        img_height: meta.ImageHeight || meta.ExifImageHeight
      };
    } catch (e) {
      return null;
    }
  }

  async function collectDeviceSignals() {
    const signals = {};
    if (typeof navigator !== 'undefined') {
      signals.platform = navigator.platform;
      signals.languages = navigator.languages?.slice(0, 3);
      signals.touch_points = navigator.maxTouchPoints;
      signals.cores = navigator.hardwareConcurrency;
      signals.memory_gb = navigator.deviceMemory;
      if (navigator.connection) {
        signals.connection_type = navigator.connection.effectiveType;
        signals.downlink_mbps = navigator.connection.downlink;
        signals.rtt_ms = navigator.connection.rtt;
      }
    }
    if (typeof screen !== 'undefined') {
      signals.screen_w = screen.width;
      signals.screen_h = screen.height;
      signals.dpr = window.devicePixelRatio;
      signals.orientation = screen.orientation?.type;
    }
    if (typeof navigator !== 'undefined' && navigator.getBattery) {
      try {
        const bat = await navigator.getBattery();
        signals.battery_level = bat.level;
        signals.battery_charging = bat.charging;
      } catch {}
    }
    return signals;
  }

  async function captureCompassHeading() {
    if (typeof DeviceOrientationEvent === 'undefined') return null;
    if (typeof DeviceOrientationEvent.requestPermission === 'function') {
      try {
        const perm = await DeviceOrientationEvent.requestPermission();
        if (perm !== 'granted') return null;
      } catch { return null; }
    }
    return new Promise(resolve => {
      let received = false;
      const handler = (e) => {
        if (received) return;
        received = true;
        window.removeEventListener('deviceorientation', handler);
        resolve({
          alpha: e.alpha,
          beta: e.beta,
          gamma: e.gamma,
          compass: e.webkitCompassHeading ?? null
        });
      };
      window.addEventListener('deviceorientation', handler, { once: true });
      setTimeout(() => { if (!received) { window.removeEventListener('deviceorientation', handler); resolve(null); }}, 1500);
    });
  }

  let files = $state([]);
  let warnings = $state([]);
  let online = $state(true);

  function syncOnline() {
    if (typeof navigator !== 'undefined') {
      const was = online;
      online = navigator.onLine;
      // Auto-retry: if we have queued files + just came back online + not already uploading, retry
      if (!was && online && files.length > 0 && uploading === 'idle') {
        console.log('[kontact] back online — retrying queued upload');
        queueMicrotask(() => upload());
      }
    }
  }

  onMount(() => {
    syncOnline();
    window.addEventListener('online', syncOnline);
    window.addEventListener('offline', syncOnline);
  });
  onDestroy(() => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('online', syncOnline);
      window.removeEventListener('offline', syncOnline);
    }
  });
  let uploading = $state('idle');
  let result = $state(null);
  let fileInput;
  let cameraInput;
  let libraryInput;
  let uploadError = $state('');
  let uploadProgress = $state(0);
  let dragOver = $state(false);
  let gettingGeo = $state(false);
  let uploadGeo = $state(null);
  let uploadAttempted = $state(false);

  // Client-side image compression — biggest mobile-upload speedup.
  // iPhone HEIC/JPEG 6-12 MB → ~400 KB at 2000px max + JPEG q=0.85.
  // QR/OCR/EXIF/LLM extraction still works at this resolution.
  let fastMode = $state(true);
  if (typeof window !== 'undefined') {
    try {
      const v = localStorage.getItem('kontact-fast-mode');
      if (v !== null) fastMode = v === '1';
    } catch {}
  }
  $effect(() => {
    if (typeof window !== 'undefined') {
      try { localStorage.setItem('kontact-fast-mode', fastMode ? '1' : '0'); } catch {}
    }
  });

  const MAX_DIM = 2000;
  const JPEG_QUALITY = 0.85;
  const COMPRESS_CONCURRENCY = 4;  // simultaneous compressions on phone

  // Pool of N async workers — throttles CPU on phone
  async function pool(items, fn, concurrency) {
    const results = new Array(items.length);
    let idx = 0;
    async function worker() {
      while (idx < items.length) {
        const i = idx++;
        results[i] = await fn(items[i], i);
      }
    }
    await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, () => worker()));
    return results;
  }

  // Upload phases (drives overlay): 'idle' | 'compressing' | 'uploading'
  let phase = $state('idle');
  let compressDone = $state(0);
  let compressTotal = $state(0);

  async function compressImage(file) {
    // Skip if not image, already small, or fast mode off
    if (!file || !file.type || !file.type.startsWith('image/')) return file;
    if (!fastMode) return file;
    if (file.size < 500_000) return file;  // < 500KB, leave alone
    try {
      let bitmap;
      if (typeof createImageBitmap === 'function') {
        bitmap = await createImageBitmap(file);
      } else {
        const url = URL.createObjectURL(file);
        const img = new Image();
        await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = url; });
        bitmap = img;
        URL.revokeObjectURL(url);
      }
      const w = bitmap.width;
      const h = bitmap.height;
      if (w <= MAX_DIM && h <= MAX_DIM && file.size < 1_500_000) {
        // Already small enough
        if (bitmap.close) bitmap.close();
        return file;
      }
      const ratio = Math.min(MAX_DIM / w, MAX_DIM / h, 1);
      const newW = Math.round(w * ratio);
      const newH = Math.round(h * ratio);
      const canvas = (typeof OffscreenCanvas !== 'undefined')
        ? new OffscreenCanvas(newW, newH)
        : (() => { const c = document.createElement('canvas'); c.width = newW; c.height = newH; return c; })();
      const ctx = canvas.getContext('2d', { alpha: false });
      ctx.drawImage(bitmap, 0, 0, newW, newH);
      if (bitmap.close) bitmap.close();
      const blob = await (canvas.convertToBlob
        ? canvas.convertToBlob({ type: 'image/jpeg', quality: JPEG_QUALITY })
        : new Promise(r => canvas.toBlob(r, 'image/jpeg', JPEG_QUALITY)));
      // Preserve original filename but switch to .jpg
      const base = (file.name || 'upload').replace(/\.[^.]+$/, '');
      return new File([blob], `${base}.jpg`, { type: 'image/jpeg' });
    } catch (err) {
      console.warn('compress failed, sending original', err);
      return file;
    }
  }

  async function getGeo() {
    if (typeof navigator === 'undefined' || !('geolocation' in navigator)) return {};
    return new Promise(resolve => {
      navigator.geolocation.getCurrentPosition(
        pos => resolve({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
          heading: pos.coords.heading ?? undefined
        }),
        () => resolve({}),
        { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 }
      );
    });
  }

  function checkImageQuality(fileList) {
    for (const file of fileList) {
      if (file.size < 10000) {
        warnings = [...warnings, { name: file.name, reason: `too small (${(file.size / 1024).toFixed(1)}KB)` }];
        continue;
      }
      const img = new Image();
      const url = URL.createObjectURL(file);
      img.onload = () => {
        if (img.width < 200 || img.height < 200) {
          warnings = [...warnings, { name: file.name, reason: `low resolution (${img.width}x${img.height}px)` }];
        }
        URL.revokeObjectURL(url);
      };
      img.onerror = () => URL.revokeObjectURL(url);
      img.src = url;
    }
  }

  function handleFiles(event) {
    const selected = Array.from(event.target.files ?? []);
    if (!selected.length) return;
    checkImageQuality(selected);
    // Fire-and-forget: enqueue to global tray. User can keep picking more.
    uploadQueue.setFastMode(fastMode);
    uploadQueue.enqueue(selected, tradeShow);
    // Clear input so same file can be re-selected later
    if (event.target) event.target.value = '';
  }

  function handleDrop(event) {
    event.preventDefault();
    dragOver = false;
    const dropped = Array.from(event.dataTransfer.files).filter(f => f.type.startsWith('image/') || f.type === 'application/pdf');
    if (!dropped.length) return;
    checkImageQuality(dropped);
    uploadQueue.setFastMode(fastMode);
    uploadQueue.enqueue(dropped, tradeShow);
  }

  function handleDragOver(event) {
    event.preventDefault();
    dragOver = true;
  }
  function handleDragLeave() { dragOver = false; }

  function removeFile(index) {
    const removed = files[index];
    files = files.filter((_, i) => i !== index);
    if (removed) {
      warnings = warnings.filter(w => w.name !== removed.name);
    }
  }

  function getThumbnailUrl(file) {
    return URL.createObjectURL(file);
  }

  // Persisted trade-show name (autofills next upload)
  let tradeShow = $state('');
  if (typeof window !== 'undefined') {
    try { tradeShow = localStorage.getItem('kontact-trade-show') || ''; } catch {}
  }
  $effect(() => {
    if (typeof window !== 'undefined') {
      try { localStorage.setItem('kontact-trade-show', tradeShow); } catch {}
    }
  });

  async function upload() {
    if (files.length === 0 || uploading === 'uploading') return;
    uploading = 'uploading';
    uploadError = '';
    uploadProgress = 0;
    try {
      // Compress with throttled pool (4 concurrent) to keep phone CPU responsive
      const beforeBytes = files.reduce((n, f) => n + (f.size || 0), 0);
      // Pre-flight size warning for very large batches
      if (beforeBytes > 500_000_000 && !confirm(
        `You are about to upload ${(beforeBytes/1e6).toFixed(0)} MB across ${files.length} files. Continue?`
      )) {
        uploading = 'idle';
        return;
      }
      phase = 'compressing';
      compressDone = 0;
      compressTotal = files.length;
      const compressed = await pool(files, async (f) => {
        const out = await compressImage(f);
        compressDone += 1;
        return out;
      }, COMPRESS_CONCURRENCY);
      const afterBytes = compressed.reduce((n, f) => n + (f.size || 0), 0);
      if (beforeBytes > 0 && afterBytes < beforeBytes) {
        const saved = Math.round((1 - afterBytes / beforeBytes) * 100);
        console.log(`[kontact] compressed ${(beforeBytes/1e6).toFixed(1)}MB → ${(afterBytes/1e6).toFixed(1)}MB (-${saved}%)`);
      }
      phase = 'uploading';
      const formData = new FormData();
      for (const file of compressed) {
        formData.append('files', file);
      }
      if (tradeShow.trim()) formData.append('trade_show', tradeShow.trim());

      // Capture client geolocation + metadata
      uploadAttempted = true;
      gettingGeo = true;
      const geo = await getGeo();
      gettingGeo = false;
      uploadGeo = geo;
      if (geo.lat) {
        formData.append('client_gps_lat', String(geo.lat));
        formData.append('client_gps_lng', String(geo.lng));
        if (geo.accuracy) formData.append('client_gps_accuracy', String(geo.accuracy));
        if (geo.heading != null) formData.append('client_heading', String(geo.heading));
      }
      try {
        formData.append('client_timezone', Intl.DateTimeFormat().resolvedOptions().timeZone);
      } catch {}
      formData.append('client_timestamp', new Date().toISOString());

      // Client-side EXIF sidecars (preserves metadata even when server-side EXIF stripped)
      const sidecars = await Promise.all(files.map(readClientExif));
      const validSidecars = sidecars.filter(Boolean);
      if (validSidecars.length) {
        formData.append('client_exif', JSON.stringify(validSidecars));
      }

      // Device signals (platform, screen, network, battery, compass)
      const deviceSignals = await collectDeviceSignals();
      const orientation = await captureCompassHeading();
      if (orientation) {
        deviceSignals.compass_heading = orientation.compass;
        deviceSignals.tilt_alpha = orientation.alpha;
        deviceSignals.tilt_beta = orientation.beta;
        deviceSignals.tilt_gamma = orientation.gamma;
      }
      formData.append('client_signals', JSON.stringify(deviceSignals));

      const res = await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            uploadProgress = Math.round((e.loaded / e.total) * 100);
          }
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try { resolve(JSON.parse(xhr.responseText)); } catch { resolve({}); }
          } else {
            reject(new Error(`Upload failed (${xhr.status})`));
          }
        };
        xhr.onerror = () => reject(new Error('Network error during upload'));
        xhr.ontimeout = () => reject(new Error('Server response timed out'));
        xhr.open('POST', '/api/upload');
        xhr.withCredentials = true;
        xhr.timeout = 120_000;  // 2 min safety — abort if server hangs
        xhr.send(formData);
      });
      result = res;
      uploading = 'done';
      phase = 'idle';
      // Auto-redirect to queue after brief confirmation so user sees progress
      if (res && res.queued && res.queued > 0) {
        setTimeout(() => goto('/queue'), 900);
      }
    } catch (err) {
      console.error('Upload failed:', err);
      const msg = err instanceof Error ? err.message : 'Upload failed';
      // If offline, keep files queued + show queued banner; will auto-retry on reconnect
      if (typeof navigator !== 'undefined' && !navigator.onLine) {
        uploadError = `Offline — ${files.length} file${files.length > 1 ? 's' : ''} queued. Will retry automatically when back online.`;
      } else {
        uploadError = `${msg}. Please try again.`;
      }
      uploading = 'idle';
      phase = 'idle';
    }
  }
</script>

<svelte:head>
  <title>Upload | KONTACT</title>
</svelte:head>

<div class="upload-page">
  <header class="page-head">
    <h1 class="page-title">Upload</h1>
    <p class="page-sub">Snap or drop catalog pages, PDFs, or images.</p>
    <label class="show-input">
      <span>Trade show / batch label (optional)</span>
      <input
        type="text"
        placeholder="e.g. Canton Fair 2026, CES 2026"
        bind:value={tradeShow}
        maxlength="80"
      />
    </label>
    <label class="fast-toggle">
      <input type="checkbox" bind:checked={fastMode} />
      <span class="fast-label">
        <strong>Fast mode</strong>
        <em>compress to 2000px before sending (~95% faster on phone)</em>
      </span>
    </label>
  </header>

  {#if !online}
    <div class="banner banner-warn">
      Offline — {files.length} file{files.length === 1 ? '' : 's'} ready. Reconnect to upload.
    </div>
  {/if}

  {#if uploadQueue.hasActive}
    <div class="upload-hint">
      <span class="dot"></span>
      {uploadQueue.activeCount} uploading in background · keep adding more
    </div>
  {/if}

  {#if uploadError}
      <div class="banner banner-error">
        <span>{uploadError}</span>
        <button class="banner-dismiss" onclick={() => uploadError = ''} aria-label="dismiss">&times;</button>
      </div>
    {/if}

    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      class="hero-zone"
      class:is-over={dragOver}
      ondrop={handleDrop}
      ondragover={handleDragOver}
      ondragleave={handleDragLeave}
    >
      <button class="hero-camera" onclick={() => cameraInput.click()} type="button" aria-label="Take photo">
        <span class="hero-cam-ico">&#128247;</span>
      </button>
      <p class="hero-label">Take a photo</p>
      <p class="hero-sub">Rear camera, multi-shot</p>
      <div class="chip-row">
        <button class="chip-btn" onclick={() => libraryInput.click()} type="button">
          <span class="chip-ico">&#127748;</span>
          <span class="chip-text">Library</span>
          <span class="chip-hint">JPG · PNG · HEIC</span>
        </button>
        <button class="chip-btn" onclick={() => fileInput.click()} type="button">
          <span class="chip-ico">&#128206;</span>
          <span class="chip-text">Files</span>
          <span class="chip-hint">PDF · any image</span>
        </button>
      </div>
      <div class="info-note">
        <span class="info-ico">&#128161;</span>
        <span>
          <strong>For best metadata:</strong> use <strong>Library</strong> (preserves GPS, camera, date)
          or share via Photos → Kontact PWA. Browser <strong>Camera</strong> strips most EXIF.
        </span>
      </div>
      {#if gettingGeo}
        <p class="geo-hint">&#128205; Getting location…</p>
      {:else if uploadGeo?.lat}
        <p class="geo-hint">&#128205; Location captured (±{Math.round(uploadGeo.accuracy)}m)</p>
      {:else if uploadAttempted}
        <p class="geo-hint muted">&#128205; Location unavailable — EXIF will be used if present</p>
      {/if}
      <p class="drop-hint-row">Drag files anywhere → desktop</p>
    </div>

    <input
      bind:this={cameraInput}
      type="file"
      accept="image/*"
      capture="environment"
      multiple
      onchange={handleFiles}
      class="file-input-hidden"
    />
    <input
      bind:this={libraryInput}
      type="file"
      accept="image/*"
      multiple
      onchange={handleFiles}
      class="file-input-hidden"
    />
    <input
      bind:this={fileInput}
      type="file"
      accept="image/*,application/pdf,.pdf,.heic,.heif"
      multiple
      onchange={handleFiles}
      class="file-input-hidden"
    />

    {#if warnings.length > 0}
      <div class="warn-block">
        {#each warnings as w}
          <p class="warn-item">{w.name} may be {w.reason}</p>
        {/each}
      </div>
    {/if}

    {#if files.length > 0}
      <div class="thumb-grid">
        {#each files as file, i}
          <div class="thumb-cell">
            <img src={getThumbnailUrl(file)} alt={file.name} class="thumb-img" />
            <button class="thumb-remove" onclick={() => removeFile(i)} aria-label="remove">&times;</button>
          </div>
        {/each}
      </div>
    {/if}
</div>

{#if false}
  <div class="upload-bar" class:visible={files.length > 0 || uploading === 'uploading'}>
    <div class="upload-bar-inner">
      {#if uploading === 'uploading'}
        <div class="progress-wrap">
          <div class="progress-bar">
            <div class="progress-fill" style="width: {uploadProgress}%"></div>
          </div>
          <span class="progress-label">{uploadProgress}%</span>
        </div>
      {:else}
        <span class="file-summary">
          {files.length} file{files.length !== 1 ? 's' : ''} ready
        </span>
      {/if}
      <button
        class="send-btn upload-action"
        onclick={upload}
        disabled={files.length === 0 || uploading === 'uploading' || !online}
      >
        {uploading === 'uploading' ? 'Uploading...' : 'Upload'}
      </button>
    </div>
  </div>
{/if}

<style>
  .upload-page {
    font-family: var(--font-sans);
    max-width: 640px;
    margin: 0 auto;
    padding: 16px 16px 32px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .page-head { margin-bottom: 4px; }
  .page-title { font-size: 24px; font-weight: 600; color: var(--text); margin: 0; letter-spacing: 0; }
  .page-sub { font-size: 14px; color: var(--text-muted); margin: 4px 0 0; }
  .show-input {
    display: block;
    margin: 14px 0 0;
  }
  .show-input span {
    display: block;
    font-size: 11px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 600;
    margin-bottom: 4px;
  }
  .show-input input {
    width: 100%;
    padding: 8px 10px;
    border: 1px solid var(--border);
    border-radius: var(--r-md);
    background: var(--surface);
    color: var(--text);
    font-size: 14px;
    font-family: inherit;
  }
  .show-input input:focus {
    outline: none;
    border-color: var(--accent);
  }
  .fast-toggle {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    margin-top: 10px;
    padding: 8px 10px;
    background: var(--accent-soft, rgba(201,100,66,0.08));
    border: 1px solid var(--border);
    border-radius: var(--r-md);
    cursor: pointer;
    user-select: none;
  }
  .fast-toggle input {
    margin-top: 3px;
    accent-color: var(--accent);
    width: 16px; height: 16px;
    flex-shrink: 0;
  }
  .fast-label {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 12px;
    color: var(--text-muted);
  }
  .fast-label strong { color: var(--text); font-weight: 600; font-size: 13px; }
  .fast-label em { font-style: normal; }

  .banner {
    padding: 10px 14px;
    border-radius: var(--r-md);
    font-size: 13px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }
  .banner-warn {
    background: rgba(181,133,61,0.08);
    border: 1px solid var(--warning);
    color: var(--warning);
  }
  .banner-error {
    background: rgba(181,69,61,0.08);
    border: 1px solid var(--danger);
    color: var(--danger);
  }
  .banner-dismiss {
    background: none; border: none;
    color: inherit; cursor: pointer;
    font-size: 18px; line-height: 1;
    padding: 0 4px;
  }

  .hero-zone {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    border: 2px dashed var(--border-strong);
    border-radius: var(--r-lg);
    background: var(--surface);
    padding: 32px 20px 20px;
    text-align: center;
    transition: background 0.15s, border-color 0.15s;
  }
  .hero-zone.is-over {
    border-color: var(--accent);
    background: var(--accent-soft);
  }
  .hero-camera {
    width: 96px;
    height: 96px;
    border-radius: 50%;
    background: var(--accent);
    color: #fff;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 6px 18px rgba(201,100,66,0.32);
    transition: transform 0.08s, box-shadow 0.15s;
    position: relative;
    overflow: hidden;
  }
  .hero-camera:hover { box-shadow: 0 8px 22px rgba(201,100,66,0.42); }
  .hero-camera:active { transform: scale(0.94); }
  .hero-camera::after {
    content: "";
    position: absolute; inset: 0;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(255,255,255,0.5) 10%, transparent 60%);
    opacity: 0;
    transform: scale(0.6);
    transition: opacity 0.4s, transform 0.4s;
  }
  .hero-camera:active::after {
    opacity: 1; transform: scale(1.4);
    transition: opacity 0s, transform 0s;
  }
  .hero-cam-ico {
    font-size: 40px;
    line-height: 1;
    filter: grayscale(1) brightness(3);
  }
  .hero-label {
    margin: 14px 0 2px;
    font-size: 17px;
    font-weight: 600;
    color: var(--text);
  }
  .hero-sub {
    margin: 0 0 18px;
    font-size: 13px;
    color: var(--text-muted);
  }
  .chip-row {
    display: flex;
    gap: 10px;
    width: 100%;
    max-width: 360px;
  }
  .chip-btn {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    padding: 12px 8px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--r-md);
    color: var(--text);
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s, transform 0.05s;
    position: relative;
    overflow: hidden;
  }
  .chip-btn:hover { border-color: var(--accent); background: var(--accent-soft); }
  .chip-btn:active { transform: scale(0.97); }
  .chip-btn::after {
    content: "";
    position: absolute; inset: 0;
    background: radial-gradient(circle at center, var(--accent-soft) 10%, transparent 70%);
    opacity: 0;
    transition: opacity 0.25s;
  }
  .chip-btn:active::after { opacity: 0.8; transition: opacity 0s; }
  .chip-ico { font-size: 20px; line-height: 1; }
  .chip-text { font-size: 13px; font-weight: 600; color: var(--text); }
  .chip-hint { font-size: 11px; color: var(--text-faint); letter-spacing: 0.02em; }
  .drop-hint-row {
    margin: 16px 0 0;
    font-size: 11px;
    color: var(--text-faint);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .info-note {
    margin-top: 14px;
    padding: 10px 12px;
    background: var(--accent-soft);
    border-radius: var(--r-md);
    font-size: 12px;
    color: var(--text);
    line-height: 1.5;
    display: flex;
    gap: 8px;
    align-items: flex-start;
    text-align: left;
  }
  .info-note strong { color: var(--accent); }
  .info-ico { font-size: 16px; line-height: 1.3; }
  .geo-hint {
    margin: 10px 0 0;
    font-size: 12px;
    color: var(--text-muted);
    font-weight: 500;
  }
  .geo-hint.muted { color: var(--text-faint); }

  .file-input-hidden {
    position: absolute; width: 1px; height: 1px;
    overflow: hidden; clip: rect(0 0 0 0);
    white-space: nowrap; border: 0;
  }

  .warn-block {
    background: rgba(181,133,61,0.08);
    border: 1px solid var(--warning);
    border-radius: var(--r-md);
    padding: 10px 14px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .warn-item {
    font-size: 13px;
    color: var(--warning);
    margin: 0;
    line-height: 1.4;
  }

  .thumb-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    padding: 4px 0 88px;
  }
  @media (max-width: 420px) {
    .thumb-grid { grid-template-columns: repeat(3, 1fr); }
  }
  .thumb-cell {
    position: relative;
    aspect-ratio: 1 / 1;
    border: 1px solid var(--border);
    border-radius: var(--r-sm);
    overflow: hidden;
    background: var(--surface);
  }
  .thumb-img {
    width: 100%; height: 100%;
    object-fit: cover; display: block;
  }
  .thumb-remove {
    position: absolute;
    top: 4px; right: 4px;
    width: 22px; height: 22px;
    background: rgba(44,43,38,0.7);
    color: #fff;
    border: none;
    border-radius: 50%;
    font-size: 14px;
    line-height: 1;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer;
    padding: 0;
  }

  .upload-bar {
    position: fixed;
    left: 0; right: 0; bottom: 0;
    background: color-mix(in srgb, var(--bg) 92%, transparent);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border-top: 1px solid var(--border);
    padding: 10px 16px calc(10px + env(safe-area-inset-bottom));
    transform: translateY(110%);
    transition: transform 0.25s ease;
    z-index: 40;
  }
  .upload-bar.visible { transform: translateY(0); }
  .upload-bar-inner {
    max-width: 640px;
    margin: 0 auto;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  @media (min-width: 768px) {
    .upload-bar { left: 240px; }
  }
  .file-summary {
    flex: 1;
    font-size: 13px;
    color: var(--text-muted);
    font-weight: 500;
  }
  .upload-action {
    min-width: 140px;
    min-height: 44px;
    font-size: 14px;
    font-weight: 600;
  }
  .progress-wrap {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .progress-bar {
    flex: 1;
    height: 6px;
    background: var(--surface-2);
    border-radius: var(--r-pill);
    overflow: hidden;
  }
  .progress-fill {
    height: 100%;
    background: var(--accent);
    transition: width 0.2s ease;
  }
  .progress-label {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-muted);
    min-width: 36px;
    text-align: right;
  }

  .success-block {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    padding: 32px 20px;
    text-align: center;
  }
  .success-icon {
    font-size: 44px;
    line-height: 1;
    color: var(--accent);
    font-weight: 600;
  }
  .success-text {
    font-size: 20px;
    font-weight: 600;
    color: var(--text);
    margin: 0;
  }
  .file-count {
    font-size: 14px;
    color: var(--text-muted);
    margin: 0;
  }
  .skipped-block {
    margin-top: 12px;
    padding: 10px 12px;
    background: rgba(181, 69, 61, 0.06);
    border: 1px solid var(--danger);
    border-radius: var(--r-md);
    text-align: left;
  }
  .skipped-title {
    font-size: 12px;
    font-weight: 600;
    color: var(--danger);
    margin: 0 0 6px;
  }
  .skipped-list {
    font-size: 12px;
    color: var(--text-muted);
    margin: 0;
    padding-left: 18px;
  }
  .success-actions {
    display: flex; gap: 8px; margin-top: 8px;
    flex-wrap: wrap; justify-content: center;
  }

  /* Upload progress overlay (full-page) */
  .upload-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.55);
    backdrop-filter: blur(4px);
    z-index: 150;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
  }
  .upload-overlay-inner {
    background: var(--surface);
    border-radius: var(--r-lg);
    padding: 28px 24px;
    max-width: 340px;
    width: 100%;
    text-align: center;
    box-shadow: 0 24px 64px rgba(0,0,0,0.4);
  }
  .upload-ring {
    position: relative;
    width: 120px;
    height: 120px;
    margin: 0 auto 14px;
  }
  .upload-ring svg {
    transform: rotate(-90deg);
  }
  .upload-ring.spin svg {
    animation: upload-ring-spin 1s linear infinite;
  }
  @keyframes upload-ring-spin {
    from { transform: rotate(-90deg); }
    to   { transform: rotate(270deg); }
  }
  .upload-ring .ring-bg {
    fill: none;
    stroke: var(--border);
    stroke-width: 8;
  }
  .upload-ring .ring-fg {
    fill: none;
    stroke: var(--accent);
    stroke-width: 8;
    stroke-linecap: round;
    transition: stroke-dashoffset 0.25s ease;
  }
  .upload-pct {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
    font-weight: 700;
    color: var(--text);
    font-family: var(--font-serif, Georgia, serif);
  }
  .upload-line {
    font-size: 15px;
    font-weight: 600;
    color: var(--text);
    margin: 0;
  }
  .upload-sub {
    font-size: 12px;
    color: var(--text-muted);
    margin: 4px 0 0;
  }
</style>
