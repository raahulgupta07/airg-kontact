<script lang="ts">
  import { uploadQueue } from '$lib/uploadQueue.svelte';
  import { goto } from '$app/navigation';

  function fmtBytes(n: number) {
    if (!n) return '';
    if (n < 1024) return `${n} B`;
    if (n < 1_048_576) return `${(n / 1024).toFixed(0)} KB`;
    return `${(n / 1_048_576).toFixed(1)} MB`;
  }

  function statusIcon(s: string) {
    return s === 'done' ? '✓'
      : s === 'error' ? '⚠'
      : s === 'queued' ? '⧗'
      : s === 'compressing' ? '⚙'
      : s === 'cancelled' ? '⊘'
      : '⟳';
  }

  function toggle() {
    uploadQueue.trayOpen = !uploadQueue.trayOpen;
  }

  function dismissAll() {
    uploadQueue.dismissCompleted();
    uploadQueue.trayOpen = false;
  }
</script>

{#if uploadQueue.hasAny}
  {@const pct = uploadQueue.aggregatePct}
  {@const active = uploadQueue.activeCount}
  {@const done = uploadQueue.doneCount}
  {@const errors = uploadQueue.errorCount}
  {@const total = uploadQueue.jobs.length}
  {@const allDone = active === 0 && errors === 0}

  <div class="tray-wrap" class:expanded={uploadQueue.trayOpen}>
    {#if !uploadQueue.trayOpen}
      <button class="tray-pill" class:tray-pill-error={errors > 0} class:tray-pill-done={allDone} onclick={toggle}>
        <span class="tray-pill-icon">
          {#if errors > 0}⚠
          {:else if allDone}✓
          {:else}<span class="mini-ring"></span>
          {/if}
        </span>
        <span class="tray-pill-text">
          {#if errors > 0}
            {errors} failed
          {:else if allDone}
            {done} uploaded
          {:else}
            {active} uploading · {pct}%
          {/if}
        </span>
        <span class="tray-pill-caret">⌃</span>
      </button>

      {#if !allDone}
        <div class="tray-pill-bar">
          <div class="tray-pill-bar-fill" style="width:{pct}%"></div>
        </div>
      {/if}
    {:else}
      <div class="tray-panel">
        <div class="tray-head">
          <strong>Uploads</strong>
          <span class="tray-sub">{done} of {total}{errors > 0 ? ` · ${errors} failed` : ''}</span>
          <div class="spacer"></div>
          <button class="icon-btn" onclick={toggle} aria-label="Collapse">⌄</button>
          {#if allDone}
            <button class="icon-btn" onclick={dismissAll} aria-label="Dismiss">✕</button>
          {/if}
        </div>
        <div class="tray-list">
          {#each uploadQueue.jobs as job (job.id)}
            <div class="tray-row" class:tr-error={job.status === 'error'} class:tr-done={job.status === 'done'}>
              <span class="tr-icon" class:spin={job.status === 'uploading' || job.status === 'compressing'}>
                {statusIcon(job.status)}
              </span>
              <div class="tr-meta">
                <div class="tr-name" title={job.name}>{job.name}</div>
                <div class="tr-sub">
                  {#if job.status === 'queued'}queued
                  {:else if job.status === 'compressing'}compressing…
                  {:else if job.status === 'uploading'}{job.progress}%
                  {:else if job.status === 'done'}done · {fmtBytes(job.compressedSize ?? job.size)}
                  {:else if job.status === 'error'}{job.error || 'failed'}
                  {:else if job.status === 'cancelled'}cancelled
                  {/if}
                </div>
                {#if job.status === 'uploading' || job.status === 'compressing'}
                  <div class="tr-bar"><div class="tr-bar-fill" style="width:{job.progress}%"></div></div>
                {/if}
              </div>
              <div class="tr-actions">
                {#if job.status === 'error'}
                  <button class="icon-btn small" onclick={() => uploadQueue.retry(job.id)} title="Retry">↻</button>
                {:else if job.status === 'queued' || job.status === 'uploading' || job.status === 'compressing'}
                  <button class="icon-btn small" onclick={() => uploadQueue.cancel(job.id)} title="Cancel">✕</button>
                {:else if job.status === 'done' && job.batchId}
                  <button class="icon-btn small" onclick={() => goto(`/queue#${job.batchId}`)} title="View">→</button>
                {/if}
              </div>
            </div>
          {/each}
        </div>
        {#if allDone}
          <div class="tray-foot">
            <button class="footer-btn" onclick={() => goto('/queue')}>View queue</button>
            <button class="footer-btn ghost" onclick={dismissAll}>Dismiss</button>
          </div>
        {/if}
      </div>
    {/if}
  </div>
{/if}

<style>
  .tray-wrap {
    position: fixed;
    bottom: 16px;
    right: 16px;
    z-index: 90;
    font-family: var(--font-sans);
  }
  @media (max-width: 720px) {
    .tray-wrap {
      bottom: 80px;   /* sit above mobile bottom nav */
      right: 10px;
      left: 10px;
    }
  }

  /* Collapsed pill */
  .tray-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 14px;
    background: var(--surface);
    border: 1px solid var(--accent);
    border-radius: 999px;
    color: var(--text);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    box-shadow: 0 6px 20px rgba(0,0,0,0.14);
    transition: transform 0.1s;
  }
  .tray-pill:hover { transform: translateY(-1px); }
  .tray-pill-error { border-color: var(--danger); }
  .tray-pill-done { border-color: var(--success, #22c55e); }
  .tray-pill-icon { display: inline-flex; align-items: center; justify-content: center; width: 16px; }
  .tray-pill-caret { color: var(--text-muted); font-size: 11px; }
  .mini-ring {
    width: 12px; height: 12px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    display: inline-block;
    animation: mini-spin 0.7s linear infinite;
  }
  @keyframes mini-spin { to { transform: rotate(360deg); } }

  .tray-pill-bar {
    margin-top: 4px;
    height: 3px;
    background: var(--border);
    border-radius: 2px;
    overflow: hidden;
  }
  .tray-pill-bar-fill {
    height: 100%;
    background: var(--accent);
    transition: width 0.25s ease;
  }
  @media (max-width: 720px) {
    .tray-pill { width: 100%; justify-content: space-between; }
  }

  /* Expanded panel */
  .tray-panel {
    width: 360px;
    max-width: calc(100vw - 24px);
    max-height: 70vh;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-lg, 12px);
    box-shadow: 0 16px 40px rgba(0,0,0,0.22);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  @media (max-width: 720px) {
    .tray-panel { width: 100%; max-height: 60vh; }
  }
  .tray-head {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 14px;
    border-bottom: 1px solid var(--border);
    font-size: 14px;
  }
  .tray-head strong { font-weight: 600; }
  .tray-sub { color: var(--text-muted); font-size: 12px; }
  .spacer { flex: 1; }
  .icon-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    width: 28px;
    height: 28px;
    border-radius: var(--r-sm, 6px);
    font-size: 16px;
  }
  .icon-btn:hover { background: var(--surface-2, rgba(0,0,0,0.04)); color: var(--text); }
  .icon-btn.small { width: 24px; height: 24px; font-size: 13px; }

  .tray-list {
    overflow-y: auto;
    padding: 4px 0;
  }
  .tray-row {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 8px 14px;
    font-size: 13px;
    border-bottom: 1px solid var(--border);
  }
  .tray-row:last-child { border-bottom: none; }
  .tr-icon {
    flex-shrink: 0;
    width: 18px;
    text-align: center;
    color: var(--accent);
    font-weight: 600;
    margin-top: 1px;
  }
  .tr-icon.spin { display: inline-block; animation: mini-spin 1.1s linear infinite; }
  .tr-done .tr-icon { color: var(--success, #22c55e); }
  .tr-error .tr-icon { color: var(--danger); }
  .tr-meta { flex: 1; min-width: 0; }
  .tr-name {
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text);
  }
  .tr-sub { color: var(--text-muted); font-size: 11px; margin-top: 1px; }
  .tr-bar {
    height: 3px;
    background: var(--border);
    border-radius: 2px;
    overflow: hidden;
    margin-top: 4px;
  }
  .tr-bar-fill { height: 100%; background: var(--accent); transition: width 0.2s; }
  .tr-actions { display: flex; align-items: center; flex-shrink: 0; }

  .tray-foot {
    display: flex;
    gap: 8px;
    padding: 10px 14px;
    border-top: 1px solid var(--border);
  }
  .footer-btn {
    flex: 1;
    padding: 7px 10px;
    border: 1px solid var(--accent);
    background: var(--accent);
    color: white;
    border-radius: var(--r-md, 8px);
    font-weight: 600;
    font-size: 13px;
    cursor: pointer;
  }
  .footer-btn.ghost {
    background: transparent;
    color: var(--text);
    border-color: var(--border);
  }
</style>
