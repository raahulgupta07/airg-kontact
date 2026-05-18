<script lang="ts">
  import { onMount } from 'svelte';
  import * as api from '$lib/api';

  let notes: api.Note[] = $state([]);
  let loading = $state(true);
  let error = $state('');
  let toast = $state('');

  let form = $state({ entity_type: 'document', entity_uuid: '', body: '' });
  let editingUuid = $state<string | null>(null);
  let editBody = $state('');

  async function load() {
    try {
      notes = await api.getNotes();
    } catch (e: any) {
      error = e?.message || 'Failed to load';
      notes = [];
    } finally {
      loading = false;
    }
  }

  onMount(load);

  function showToast(m: string) { toast = m; setTimeout(() => (toast = ''), 2000); }

  async function save() {
    if (!form.entity_uuid.trim() || !form.body.trim()) return;
    try {
      await api.createNote({ ...form });
      form = { entity_type: form.entity_type, entity_uuid: '', body: '' };
      showToast('Note created');
      await load();
    } catch (e: any) { showToast('Failed: ' + e.message); }
  }

  async function remove(uuid: string) {
    try {
      await api.deleteNote(uuid);
      showToast('Deleted');
      await load();
    } catch (e: any) { showToast('Failed: ' + e.message); }
  }

  function beginEdit(n: api.Note) {
    editingUuid = n.uuid;
    editBody = n.body;
  }

  async function saveEdit() {
    if (!editingUuid) return;
    try {
      await api.updateNote(editingUuid, { body: editBody });
      editingUuid = null;
      showToast('Saved');
      await load();
    } catch (e: any) { showToast('Failed: ' + e.message); }
  }
</script>

<div class="card">
  <h2>Notes</h2>

  <div class="form">
    <label>Entity type
      <select class="input" bind:value={form.entity_type}>
        <option value="document">document</option>
        <option value="contact">contact</option>
        <option value="company">company</option>
        <option value="product">product</option>
        <option value="meeting">meeting</option>
      </select>
    </label>
    <label>Entity UUID
      <input class="input" bind:value={form.entity_uuid} placeholder="paste uuid" />
    </label>
    <label class="full">Body
      <textarea class="input" rows="3" bind:value={form.body} placeholder="Note..."></textarea>
    </label>
    <button class="send-btn" onclick={save} disabled={!form.entity_uuid.trim() || !form.body.trim()}>Add note</button>
  </div>

  {#if loading}
    <p class="muted">Loading...</p>
  {:else if error}
    <p class="muted">{error}</p>
  {:else if !notes.length}
    <p class="muted">No notes yet.</p>
  {:else}
    <ul class="note-list">
      {#each notes as n}
        <li class="note-item">
          <div class="note-meta">
            <span class="chip chip-accent">{n.entity_type}</span>
            <span class="uuid">{(n.entity_uuid || '').slice(0, 8)}</span>
            {#if n.created_at}<span class="muted">· {new Date(n.created_at).toLocaleString()}</span>{/if}
          </div>
          {#if editingUuid === n.uuid}
            <textarea class="input" rows="3" bind:value={editBody}></textarea>
            <div class="actions">
              <button class="btn-ghost xs" onclick={() => (editingUuid = null)}>Cancel</button>
              <button class="send-btn" onclick={saveEdit}>Save</button>
            </div>
          {:else}
            <p class="body">{n.body}</p>
            <div class="actions">
              <button class="btn-ghost xs" onclick={() => beginEdit(n)}>Edit</button>
              <button class="btn-ghost xs danger" onclick={() => remove(n.uuid)}>Delete</button>
            </div>
          {/if}
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
  .form { display: grid; grid-template-columns: 1fr 1fr auto; gap: 10px; padding: 12px; background: var(--surface-2); border-radius: var(--r-md); border: 1px solid var(--border); margin-bottom: 14px; align-items: end; }
  .form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-muted); }
  .form label.full { grid-column: 1 / -1; }
  @media (max-width: 700px) { .form { grid-template-columns: 1fr; } }
  .note-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
  .note-item { padding: 10px 12px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--r-md); }
  .note-meta { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; font-size: 11px; }
  .chip-accent { padding: 2px 8px; background: var(--accent-soft); color: var(--accent-ink); border-radius: var(--r-pill); font-size: 11px; }
  .uuid { font-family: var(--font-mono); color: var(--text-muted); }
  .body { margin: 4px 0 8px; font-size: 13px; color: var(--text); white-space: pre-wrap; }
  .actions { display: flex; gap: 6px; justify-content: flex-end; }
  .btn-ghost.xs { padding: 4px 10px; font-size: 11px; min-height: 26px; }
  .btn-ghost.xs.danger { color: var(--danger); border-color: var(--danger); }
  .toast { position: fixed; bottom: 24px; right: 24px; background: var(--accent); color: #fff; padding: 10px 16px; border-radius: var(--r-md); font-size: 13px; z-index: 400; }
</style>
