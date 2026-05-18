<script lang="ts">
  import { onMount } from 'svelte';
  import * as api from '$lib/api';

  let groups: api.TimelineGroup[] = $state([]);
  let loading = $state(true);
  let error = $state('');

  onMount(async () => {
    try {
      groups = await api.getTimeline();
    } catch (e: any) {
      error = e?.message || 'Failed to load';
    } finally {
      loading = false;
    }
  });

  function fmtDate(d: string) {
    try {
      return new Date(d).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
    } catch {
      return d;
    }
  }
</script>

<div class="card">
  <h2>Timeline</h2>
  {#if loading}
    <p class="muted">Loading...</p>
  {:else if error}
    <p class="muted">{error}</p>
  {:else if !groups.length}
    <p class="muted">No dated documents yet.</p>
  {:else}
    <div class="timeline">
      {#each groups as g}
        <div class="day-card">
          <div class="day-head">
            <strong>{fmtDate(g.date)}</strong>
            <span class="chip chip-accent">{g.doc_count} docs</span>
          </div>
          <div class="batches">
            {#each g.batches as b}
              <a class="batch-chip" href={`/queue?batch=${encodeURIComponent(b.batch_id)}`}>
                {b.batch_id.slice(0, 10)} · {b.count}
              </a>
            {/each}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 16px; }
  .card h2 { margin: 0 0 12px; font-size: 16px; font-weight: 600; }
  .muted { color: var(--text-muted); font-size: 13px; }
  .timeline { display: flex; flex-direction: column; gap: 10px; }
  .day-card { padding: 12px 14px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--r-md); }
  .day-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 14px; }
  .chip-accent { display: inline-block; padding: 2px 10px; border-radius: var(--r-pill); background: var(--accent-soft); color: var(--accent-ink); font-size: 11px; }
  .batches { display: flex; flex-wrap: wrap; gap: 6px; }
  .batch-chip { padding: 4px 10px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-pill); font-size: 12px; color: var(--text); text-decoration: none; font-family: var(--font-mono); }
  .batch-chip:hover { background: var(--accent-soft); color: var(--accent-ink); border-color: var(--accent); }
</style>
