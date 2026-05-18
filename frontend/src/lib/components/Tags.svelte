<script lang="ts">
  import { onMount } from 'svelte';
  import * as api from '$lib/api';

  let tags: api.Tag[] = $state([]);
  let loading = $state(true);
  let error = $state('');
  let toast = $state('');

  let newName = $state('');
  let newColor = $state('#C96442');

  async function load() {
    try {
      tags = await api.getTags();
    } catch (e: any) {
      error = e?.message || 'Failed to load';
      tags = [];
    } finally {
      loading = false;
    }
  }

  onMount(load);

  function showToast(m: string) { toast = m; setTimeout(() => (toast = ''), 2000); }

  async function add() {
    if (!newName.trim()) return;
    try {
      await api.createTag(newName.trim(), newColor);
      newName = '';
      showToast('Tag created');
      await load();
    } catch (e: any) { showToast('Failed: ' + e.message); }
  }

  async function remove(uuid: string) {
    try {
      await api.deleteTag(uuid);
      showToast('Deleted');
      await load();
    } catch (e: any) { showToast('Failed: ' + e.message); }
  }
</script>

<div class="card">
  <h2>Tags</h2>

  <div class="form">
    <input class="input" placeholder="Tag name..." bind:value={newName} onkeydown={(e) => e.key === 'Enter' && add()} />
    <input class="input color-input" type="color" bind:value={newColor} />
    <button class="send-btn" onclick={add} disabled={!newName.trim()}>Add</button>
  </div>

  {#if loading}
    <p class="muted">Loading...</p>
  {:else if error}
    <p class="muted">{error}</p>
  {:else if !tags.length}
    <p class="muted">No tags yet. Add one above.</p>
  {:else}
    <ul class="tag-list">
      {#each tags as t}
        <li class="tag-item">
          <span class="swatch" style:background={t.color || 'var(--accent)'}></span>
          <strong class="name">{t.name}</strong>
          {#if t.doc_count !== undefined}
            <span class="chip">{t.doc_count}</span>
          {/if}
          <button class="btn-ghost xs danger" onclick={() => remove(t.uuid)}>Delete</button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

{#if toast}<div class="toast">{toast}</div>{/if}

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 16px; }
  .card h2 { margin: 0 0 12px; font-size: 16px; font-weight: 600; }
  .muted { color: var(--text-muted); font-size: 13px; }
  .form { display: flex; gap: 8px; margin-bottom: 14px; align-items: center; padding: 12px; background: var(--surface-2); border-radius: var(--r-md); border: 1px solid var(--border); }
  .form .input { flex: 1; }
  .color-input { width: 48px; min-width: 48px; padding: 4px; height: 40px; flex: 0; }
  .tag-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 6px; }
  .tag-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--r-md); }
  .swatch { width: 16px; height: 16px; border-radius: 4px; border: 1px solid var(--border); flex-shrink: 0; }
  .name { font-size: 13px; flex: 1; }
  .chip { padding: 2px 10px; background: var(--accent-soft); color: var(--accent-ink); border-radius: var(--r-pill); font-size: 11px; }
  .btn-ghost.xs { padding: 4px 10px; font-size: 11px; min-height: 26px; }
  .btn-ghost.xs.danger { color: var(--danger); border-color: var(--danger); }
  .toast { position: fixed; bottom: 24px; right: 24px; background: var(--accent); color: #fff; padding: 10px 16px; border-radius: var(--r-md); font-size: 13px; z-index: 400; }
</style>
