// Global upload queue — persistent across route navigation.
// Each enqueued file gets its own xhr. Concurrency cap keeps phone uplink sane.

export type UploadStatus = 'queued' | 'compressing' | 'uploading' | 'done' | 'error' | 'cancelled';

export interface UploadJob {
  id: string;
  file: File;
  name: string;
  size: number;          // original size
  compressedSize?: number;
  status: UploadStatus;
  progress: number;      // 0-100
  error?: string;
  tradeShow?: string;
  batchId?: string;
  result?: any;
  xhr?: XMLHttpRequest;
  startedAt?: number;
  doneAt?: number;
}

const MAX_PARALLEL = 2;
const MAX_DIM = 2000;
const JPEG_QUALITY = 0.85;

// crypto.randomUUID() requires HTTPS / localhost (secure context).
// LAN IPs over http (192.168.x.x) throw. Use fallback.
function makeId(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch {}
  return 'id-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
}

class UploadQueueState {
  jobs: UploadJob[] = $state([]);
  trayOpen: boolean = $state(false);
  fastMode: boolean = $state(true);

  constructor() {
    if (typeof window !== 'undefined') {
      try {
        const v = localStorage.getItem('kontact-fast-mode');
        if (v !== null) this.fastMode = v === '1';
      } catch {}
      window.addEventListener('online', () => this.retryOfflineErrors());
    }
  }

  setFastMode(v: boolean) {
    this.fastMode = v;
    if (typeof window !== 'undefined') {
      try { localStorage.setItem('kontact-fast-mode', v ? '1' : '0'); } catch {}
    }
  }

  get aggregatePct(): number {
    const active = this.jobs.filter(j => j.status !== 'done' && j.status !== 'cancelled' && j.status !== 'error');
    if (!active.length) return 100;
    const sum = active.reduce((a, j) => a + (j.progress || 0), 0);
    return Math.round(sum / active.length);
  }

  get activeCount(): number {
    return this.jobs.filter(j => j.status === 'compressing' || j.status === 'uploading' || j.status === 'queued').length;
  }
  get doneCount(): number {
    return this.jobs.filter(j => j.status === 'done').length;
  }
  get errorCount(): number {
    return this.jobs.filter(j => j.status === 'error').length;
  }
  get hasAny(): boolean {
    return this.jobs.length > 0;
  }
  get hasActive(): boolean {
    return this.activeCount > 0;
  }

  enqueue(files: File[], tradeShow?: string) {
    const ts = tradeShow?.trim() || undefined;
    for (const f of files) {
      const job: UploadJob = {
        id: makeId(),
        file: f,
        name: f.name || 'upload',
        size: f.size || 0,
        status: 'queued',
        progress: 0,
        tradeShow: ts,
      };
      this.jobs = [...this.jobs, job];
    }
    this.trayOpen = true;
    this.pump();
  }

  dismissCompleted() {
    this.jobs = this.jobs.filter(j => j.status !== 'done' && j.status !== 'cancelled');
  }

  cancel(id: string) {
    const j = this.jobs.find(x => x.id === id);
    if (!j) return;
    try { j.xhr?.abort(); } catch {}
    j.status = 'cancelled';
    this.jobs = [...this.jobs];
    this.pump();
  }

  retry(id: string) {
    const j = this.jobs.find(x => x.id === id);
    if (!j) return;
    j.status = 'queued';
    j.progress = 0;
    j.error = undefined;
    this.jobs = [...this.jobs];
    this.pump();
  }

  retryOfflineErrors() {
    let any = false;
    for (const j of this.jobs) {
      if (j.status === 'error' && /offline|network/i.test(j.error || '')) {
        j.status = 'queued';
        j.progress = 0;
        j.error = undefined;
        any = true;
      }
    }
    if (any) { this.jobs = [...this.jobs]; this.pump(); }
  }

  private pump() {
    const running = this.jobs.filter(j => j.status === 'compressing' || j.status === 'uploading').length;
    let slots = MAX_PARALLEL - running;
    if (slots <= 0) return;
    for (const j of this.jobs) {
      if (slots <= 0) break;
      if (j.status === 'queued') {
        this.runJob(j);
        slots -= 1;
      }
    }
  }

  private async runJob(job: UploadJob) {
    job.startedAt = Date.now();
    let blob: Blob | File = job.file;
    if (this.fastMode && job.file.type?.startsWith('image/') && job.file.size > 500_000) {
      job.status = 'compressing';
      this.jobs = [...this.jobs];
      try {
        blob = await this.compress(job.file);
        job.compressedSize = (blob as Blob).size;
      } catch (e) {
        // fall back to original
        blob = job.file;
      }
    }
    job.status = 'uploading';
    job.progress = 0;
    this.jobs = [...this.jobs];

    const fd = new FormData();
    const sendFile = blob instanceof File ? blob : new File([blob], job.name.replace(/\.[^.]+$/, '') + '.jpg', { type: 'image/jpeg' });
    fd.append('files', sendFile);
    if (job.tradeShow) fd.append('trade_show', job.tradeShow);

    const xhr = new XMLHttpRequest();
    job.xhr = xhr;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        job.progress = Math.round((e.loaded / e.total) * 100);
        this.jobs = [...this.jobs];
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { job.result = JSON.parse(xhr.responseText); } catch { job.result = {}; }
        job.batchId = job.result?.batch_id;
        job.status = 'done';
        job.progress = 100;
        job.doneAt = Date.now();
      } else {
        job.status = 'error';
        job.error = `Server ${xhr.status}`;
      }
      this.jobs = [...this.jobs];
      this.pump();
      this.maybeAutoHide();
    };
    xhr.onerror = () => {
      const offline = typeof navigator !== 'undefined' && !navigator.onLine;
      job.status = 'error';
      job.error = offline ? 'Offline — will retry on reconnect' : 'Network error';
      this.jobs = [...this.jobs];
      this.pump();
    };
    xhr.ontimeout = () => {
      job.status = 'error';
      job.error = 'Server response timed out';
      this.jobs = [...this.jobs];
      this.pump();
    };
    xhr.timeout = 120_000;
    xhr.open('POST', '/api/upload');
    xhr.withCredentials = true;
    xhr.send(fd);
  }

  private async compress(file: File): Promise<Blob> {
    let bitmap: any;
    if (typeof createImageBitmap === 'function') {
      bitmap = await createImageBitmap(file);
    } else {
      const url = URL.createObjectURL(file);
      const img = new Image();
      await new Promise((r, j) => { img.onload = r; img.onerror = j; img.src = url; });
      bitmap = img;
      URL.revokeObjectURL(url);
    }
    const w = bitmap.width, h = bitmap.height;
    if (w <= MAX_DIM && h <= MAX_DIM && file.size < 1_500_000) {
      if (bitmap.close) bitmap.close();
      return file;
    }
    const ratio = Math.min(MAX_DIM / w, MAX_DIM / h, 1);
    const newW = Math.round(w * ratio);
    const newH = Math.round(h * ratio);
    const canvas: any = (typeof OffscreenCanvas !== 'undefined')
      ? new OffscreenCanvas(newW, newH)
      : (() => { const c = document.createElement('canvas'); c.width = newW; c.height = newH; return c; })();
    const ctx = canvas.getContext('2d', { alpha: false });
    ctx.drawImage(bitmap, 0, 0, newW, newH);
    if (bitmap.close) bitmap.close();
    return canvas.convertToBlob
      ? canvas.convertToBlob({ type: 'image/jpeg', quality: JPEG_QUALITY })
      : new Promise<Blob>((r) => canvas.toBlob(r, 'image/jpeg', JPEG_QUALITY));
  }

  private autoHideTimer: any = null;
  private maybeAutoHide() {
    if (this.activeCount === 0 && this.errorCount === 0) {
      // All done — fade tray after 3s
      if (this.autoHideTimer) clearTimeout(this.autoHideTimer);
      this.autoHideTimer = setTimeout(() => {
        if (this.activeCount === 0 && this.errorCount === 0) {
          this.jobs = [];
          this.trayOpen = false;
        }
      }, 3000);
    }
  }
}

export const uploadQueue = new UploadQueueState();
