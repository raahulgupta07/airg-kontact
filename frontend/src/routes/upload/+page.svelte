<script>
  import { goto } from '$app/navigation';
  import { onMount, onDestroy } from 'svelte';
  import exifr from 'exifr';

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
    if (typeof navigator !== 'undefined') online = navigator.onLine;
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
    files = [...files, ...selected];
    checkImageQuality(selected);
    // Auto-submit: as soon as a file is picked, fire upload + go to queue
    queueMicrotask(() => { if (!uploading || uploading === 'idle') upload(); });
  }

  function handleDrop(event) {
    event.preventDefault();
    dragOver = false;
    const dropped = Array.from(event.dataTransfer.files).filter(f => f.type.startsWith('image/') || f.type === 'application/pdf');
    if (!dropped.length) return;
    files = [...files, ...dropped];
    checkImageQuality(dropped);
    queueMicrotask(() => { if (!uploading || uploading === 'idle') upload(); });
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

  async function upload() {
    if (files.length === 0 || uploading === 'uploading') return;
    uploading = 'uploading';
    uploadError = '';
    uploadProgress = 0;
    try {
      const formData = new FormData();
      for (const file of files) {
        formData.append('files', file);
      }

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
        xhr.open('POST', '/api/upload');
        xhr.withCredentials = true;
        xhr.send(formData);
      });
      result = res;
      uploading = 'done';
      // Auto-redirect to queue after brief confirmation so user sees progress
      if (res && res.queued && res.queued > 0) {
        setTimeout(() => goto('/queue'), 900);
      }
    } catch (err) {
      console.error('Upload failed:', err);
      uploadError = err instanceof Error ? err.message : 'Upload failed. Please try again.';
      uploading = 'idle';
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
  </header>

  {#if !online}
    <div class="banner banner-warn">
      Offline — {files.length} file{files.length === 1 ? '' : 's'} ready. Reconnect to upload.
    </div>
  {/if}

  {#if uploading === 'done' && result}
    <div class="success-block card">
      <div class="success-icon">&#10003;</div>
      <p class="success-text">Batch uploaded</p>
      <p class="file-count">{result.queued ?? files.length} of {files.length} image{files.length !== 1 ? 's' : ''} sent for processing</p>
      {#if result.skipped && result.skipped.length}
        <div class="skipped-block">
          <p class="skipped-title">Skipped {result.skipped.length}:</p>
          <ul class="skipped-list">
            {#each result.skipped as s}
              <li>{s.name} — {s.reason}</li>
            {/each}
          </ul>
        </div>
      {/if}
      <div class="success-actions">
        <button class="send-btn" onclick={() => goto('/queue')}>View queue</button>
        <button class="btn-ghost" onclick={() => {
          files = [];
          warnings = [];
          uploading = 'idle';
          result = null;
        }}>Upload more</button>
      </div>
    </div>
  {:else}
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
  {/if}
</div>

{#if uploading !== 'done'}
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
</style>
