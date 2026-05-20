<script lang="ts">
  import { onMount } from 'svelte';

  let events = $state<any[]>([]);
  let loading = $state(false);
  let typeFilter = $state('');
  let limit = $state(200);
  let toastMsg = $state('');

  function toast(m: string) { toastMsg = m; setTimeout(() => toastMsg = '', 2200); }

  async function load() {
    loading = true;
    try {
      const qs = new URLSearchParams({ limit: String(limit) });
      if (typeFilter) qs.set('type', typeFilter);
      const r = await fetch(`/api/events?${qs}`, { credentials: 'include' });
      if (r.ok) events = await r.json();
      else if (r.status === 403) toast('Admin only');
      else toast('Load failed: ' + r.status);
    } catch (e: any) {
      toast('Error: ' + e.message);
    } finally {
      loading = false;
    }
  }

  function parseDetail(s: any): string {
    if (!s) return '';
    if (typeof s === 'object') return JSON.stringify(s);
    try { return JSON.stringify(JSON.parse(s)); } catch { return String(s); }
  }

  function shortTime(ts: string): string {
    try { return new Date(ts).toLocaleString(); } catch { return ts; }
  }

  function eventChip(t: string): string {
    if (t.startsWith('backfill')) return 'chip-backfill';
    if (t.startsWith('merge')) return 'chip-merge';
    if (t === 'upload') return 'chip-upload';
    if (t.includes('login') || t.includes('password')) return 'chip-auth';
    if (t === 'delete') return 'chip-danger';
    return 'chip-default';
  }

  onMount(load);
  $effect(() => { void typeFilter; void limit; load(); });
</script>

<div class="card">
  <div class="head">
    <h2>Audit Log <span class="muted">({events.length})</span></h2>
    <div class="controls">
      <input class="input" type="text" placeholder="Filter event type (e.g. backfill_company, merge_approved)" bind:value={typeFilter} />
      <select bind:value={limit}>
        <option value={100}>100</option>
        <option value={200}>200</option>
        <option value={500}>500</option>
        <option value={1000}>1000</option>
      </select>
      <button class="btn-ghost xs" onclick={load} disabled={loading}>{loading ? '⏳' : '↻'} Refresh</button>
    </div>
  </div>

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if events.length === 0}
    <p class="muted">No events match.</p>
  {:else}
    <div class="evt-list">
      {#each events as e}
        <div class="evt">
          <span class="evt-time">{shortTime(e.ts || e.created_at)}</span>
          <span class="evt-type {eventChip(e.event_type || e.type || '')}">{e.event_type || e.type || ''}</span>
          <span class="evt-entity">{e.entity_type || ''} {e.entity_uuid ? '· ' + String(e.entity_uuid).slice(0, 8) : ''}</span>
          <span class="evt-user muted">{e.user_uuid ? String(e.user_uuid).slice(0, 8) : ''}</span>
          <span class="evt-detail" title={parseDetail(e.detail || e.detail_json)}>{parseDetail(e.detail || e.detail_json).slice(0, 120)}</span>
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if toastMsg}<div class="toast">{toastMsg}</div>{/if}

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 16px; }
  .head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
  .controls { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .input, select { padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--r-sm); background: var(--surface); color: var(--text); font-size: 13px; font-family: inherit; }
  .input { min-width: 280px; }
  .muted { color: var(--text-muted); font-size: 13px; }
  .evt-list { display: flex; flex-direction: column; gap: 4px; max-height: 70vh; overflow-y: auto; }
  .evt { display: grid; grid-template-columns: 160px 160px 1fr 100px 2fr; gap: 12px; padding: 6px 8px; border-bottom: 1px solid var(--border); font-size: 12px; align-items: center; }
  .evt-time { color: var(--text-muted); font-family: var(--font-mono); font-size: 11px; }
  .evt-type { padding: 2px 8px; border-radius: var(--r-pill); font-size: 11px; font-weight: 600; text-align: center; }
  .chip-default { background: rgba(120,120,120,0.15); color: var(--text-muted); }
  .chip-backfill { background: rgba(80,180,100,0.15); color: #50b464; }
  .chip-merge { background: rgba(201,100,66,0.15); color: var(--accent, #c96442); }
  .chip-upload { background: rgba(70,130,200,0.15); color: #4682c8; }
  .chip-auth { background: rgba(155,89,182,0.15); color: #9b59b6; }
  .chip-danger { background: rgba(220,80,80,0.15); color: #dc5050; }
  .evt-entity { font-family: var(--font-mono); font-size: 11px; }
  .evt-user { font-family: var(--font-mono); font-size: 11px; }
  .evt-detail { color: var(--text-muted); font-family: var(--font-mono); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .btn-ghost.xs { padding: 5px 10px; border-radius: var(--r-sm); font-size: 12px; cursor: pointer; background: transparent; border: 1px solid var(--border); color: var(--text); font-family: inherit; }
  .toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: var(--surface); border: 1px solid var(--border); padding: 10px 16px; border-radius: var(--r-md); box-shadow: 0 4px 16px rgba(0,0,0,0.15); z-index: 1000; }
</style>
