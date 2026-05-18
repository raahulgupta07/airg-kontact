<script lang="ts">
  import { onMount } from 'svelte';
  import * as api from '$lib/api';

  let items: api.QrItem[] = $state([]);
  let typeFilter = $state('All');
  let loading = $state(true);
  let error = $state('');

  onMount(async () => {
    try {
      items = await api.getQrCodes();
    } catch (e: any) {
      error = e?.message || 'Failed to load';
    } finally {
      loading = false;
    }
  });

  const types = $derived.by(() => {
    const s = new Set<string>();
    items.forEach((i) => { if (i.qr_type) s.add(i.qr_type); });
    return ['All', ...Array.from(s).sort()];
  });

  const filtered = $derived(typeFilter === 'All' ? items : items.filter((i) => i.qr_type === typeFilter));

  function truncate(s: string | undefined, n = 60) {
    if (!s) return '';
    return s.length > n ? s.slice(0, n) + '...' : s;
  }

  function formatParsed(p: unknown) {
    if (!p) return '';
    if (typeof p === 'string') return p;
    try { return JSON.stringify(p); } catch { return String(p); }
  }
</script>

<div class="card">
  <h2>QR codes</h2>
  <div class="toolbar">
    <label>Type
      <select class="input" bind:value={typeFilter}>
        {#each types as t}<option value={t}>{t}</option>{/each}
      </select>
    </label>
    <span class="muted">{filtered.length} of {items.length}</span>
  </div>

  {#if loading}
    <p class="muted">Loading...</p>
  {:else if error}
    <p class="muted">{error}</p>
  {:else if !filtered.length}
    <p class="muted">No QR codes detected yet.</p>
  {:else}
    <div class="table-scroll">
      <table class="data-table">
        <thead><tr><th>Source</th><th>Type</th><th>Raw</th><th>Parsed</th></tr></thead>
        <tbody>
          {#each filtered as q}
            <tr>
              <td>{q.source_file || ''}</td>
              <td><span class="chip">{q.qr_type || ''}</span></td>
              <td class="mono">{truncate(q.qr_raw)}</td>
              <td class="mono">{truncate(formatParsed(q.qr_parsed), 80)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 16px; }
  .card h2 { margin: 0 0 12px; font-size: 16px; font-weight: 600; }
  .muted { color: var(--text-muted); font-size: 13px; }
  .toolbar { display: flex; gap: 12px; align-items: end; margin-bottom: 12px; }
  .toolbar label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-muted); }
  .toolbar .input { width: 200px; }
  .table-scroll { overflow: auto; max-height: 560px; border: 1px solid var(--border); border-radius: var(--r-md); }
  .data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .data-table th { padding: 10px 12px; font-size: 12px; font-weight: 500; color: var(--text-muted); text-align: left; background: var(--surface-2); border-bottom: 1px solid var(--border); position: sticky; top: 0; }
  .data-table td { padding: 8px 12px; border-bottom: 1px solid var(--border); }
  .mono { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); word-break: break-all; max-width: 320px; }
  .chip { padding: 2px 10px; border-radius: var(--r-pill); background: var(--accent-soft); color: var(--accent-ink); font-size: 11px; }
</style>
