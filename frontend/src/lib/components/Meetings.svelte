<script lang="ts">
  import { onMount } from 'svelte';
  import * as api from '$lib/api';

  let meetings: api.Meeting[] = $state([]);
  let contacts: any[] = $state([]);
  let loading = $state(true);
  let error = $state('');
  let toast = $state('');
  let contactFilter = $state('All');

  let form = $state<Partial<api.Meeting>>({
    contact_uuid: '', date: '', location: '', notes: '', outcome: ''
  });
  let editing = $state<api.Meeting | null>(null);

  async function load() {
    try {
      meetings = await api.getMeetings();
    } catch (e: any) {
      error = e?.message || 'Failed to load';
      meetings = [];
    } finally {
      loading = false;
    }
  }

  onMount(async () => {
    await load();
    try {
      const r = await fetch('/api/contacts');
      const data = await r.json();
      contacts = Array.isArray(data) ? data : data.contacts || [];
    } catch { contacts = []; }
  });

  function showToast(m: string) { toast = m; setTimeout(() => (toast = ''), 2000); }

  async function save() {
    if (!form.date && !form.contact_uuid && !form.notes) return;
    try {
      await api.createMeeting(form);
      form = { contact_uuid: '', date: '', location: '', notes: '', outcome: '' };
      showToast('Meeting saved');
      await load();
    } catch (e: any) { showToast('Failed: ' + e.message); }
  }

  async function remove(uuid: string) {
    try {
      await api.deleteMeeting(uuid);
      showToast('Deleted');
      await load();
    } catch (e: any) { showToast('Failed: ' + e.message); }
  }

  async function saveEdit() {
    if (!editing) return;
    try {
      await api.updateMeeting(editing.uuid, editing);
      editing = null;
      showToast('Saved');
      await load();
    } catch (e: any) { showToast('Failed: ' + e.message); }
  }

  const filtered = $derived(
    contactFilter === 'All' ? meetings : meetings.filter((m) => m.contact_uuid === contactFilter)
  );
</script>

<div class="card">
  <h2>Meetings</h2>

  <div class="form">
    <label>Contact
      <select class="input" bind:value={form.contact_uuid}>
        <option value="">— select —</option>
        {#each contacts as c}
          <option value={c.uuid}>{c.person || c.company || c.uuid.slice(0, 8)}</option>
        {/each}
      </select>
    </label>
    <label>Date
      <input class="input" type="datetime-local" bind:value={form.date} />
    </label>
    <label>Location
      <input class="input" bind:value={form.location} placeholder="Booth, city..." />
    </label>
    <label>Outcome
      <input class="input" bind:value={form.outcome} placeholder="follow-up, sample, etc" />
    </label>
    <label class="full">Notes
      <textarea class="input" rows="2" bind:value={form.notes}></textarea>
    </label>
    <button class="send-btn" onclick={save}>Add meeting</button>
  </div>

  <div class="toolbar">
    <label>Filter by contact
      <select class="input" bind:value={contactFilter}>
        <option value="All">All</option>
        {#each contacts as c}
          <option value={c.uuid}>{c.person || c.company || c.uuid.slice(0, 8)}</option>
        {/each}
      </select>
    </label>
    <span class="muted">{filtered.length} of {meetings.length}</span>
  </div>

  {#if loading}
    <p class="muted">Loading...</p>
  {:else if error}
    <p class="muted">{error}</p>
  {:else if !filtered.length}
    <p class="muted">No meetings recorded.</p>
  {:else}
    <ul class="m-list">
      {#each filtered as m}
        <li class="m-item">
          <div class="m-head">
            <strong>{m.contact_name || (m.contact_uuid || '').slice(0, 8) || 'Untitled'}</strong>
            <span class="muted">{m.date || ''}</span>
          </div>
          {#if m.location}<div class="m-row">📍 {m.location}</div>{/if}
          {#if m.outcome}<div class="m-row">→ {m.outcome}</div>{/if}
          {#if m.notes}<div class="m-row notes">{m.notes}</div>{/if}
          <div class="actions">
            <button class="btn-ghost xs" onclick={() => (editing = { ...m })}>Edit</button>
            <button class="btn-ghost xs danger" onclick={() => remove(m.uuid)}>Delete</button>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</div>

{#if editing}
  <div class="modal-backdrop" onclick={() => (editing = null)} role="button" tabindex="-1" onkeydown={(e) => e.key === 'Escape' && (editing = null)}>
    <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog">
      <h3>Edit meeting</h3>
      <label>Date <input class="input" type="datetime-local" bind:value={editing.date} /></label>
      <label>Location <input class="input" bind:value={editing.location} /></label>
      <label>Outcome <input class="input" bind:value={editing.outcome} /></label>
      <label>Notes <textarea class="input" rows="3" bind:value={editing.notes}></textarea></label>
      <div class="modal-actions">
        <button class="btn-ghost" onclick={() => (editing = null)}>Cancel</button>
        <button class="send-btn" onclick={saveEdit}>Save</button>
      </div>
    </div>
  </div>
{/if}

{#if toast}<div class="toast">{toast}</div>{/if}

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 16px; }
  .card h2 { margin: 0 0 12px; font-size: 16px; font-weight: 600; }
  .muted { color: var(--text-muted); font-size: 13px; }
  .form { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; padding: 12px; background: var(--surface-2); border-radius: var(--r-md); border: 1px solid var(--border); margin-bottom: 14px; }
  .form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-muted); }
  .form label.full { grid-column: 1 / -1; }
  .form .send-btn { grid-column: 1 / -1; justify-self: end; }
  @media (max-width: 800px) { .form { grid-template-columns: 1fr 1fr; } }
  @media (max-width: 500px) { .form { grid-template-columns: 1fr; } }
  .toolbar { display: flex; gap: 12px; align-items: end; margin-bottom: 12px; }
  .toolbar label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-muted); }
  .toolbar .input { width: 220px; }
  .m-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
  .m-item { padding: 10px 12px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--r-md); font-size: 13px; }
  .m-head { display: flex; justify-content: space-between; margin-bottom: 4px; }
  .m-row { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
  .m-row.notes { white-space: pre-wrap; color: var(--text); margin-top: 6px; }
  .actions { display: flex; gap: 6px; justify-content: flex-end; margin-top: 6px; }
  .btn-ghost.xs { padding: 4px 10px; font-size: 11px; min-height: 26px; }
  .btn-ghost.xs.danger { color: var(--danger); border-color: var(--danger); }
  .modal-backdrop { position: fixed; inset: 0; background: rgba(44,43,38,0.4); backdrop-filter: blur(2px); display: flex; align-items: center; justify-content: center; z-index: 300; padding: 16px; }
  .modal { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); box-shadow: var(--shadow-lg); padding: 20px; width: 100%; max-width: 480px; display: flex; flex-direction: column; gap: 10px; }
  .modal h3 { margin: 0 0 6px; font-size: 16px; font-weight: 600; }
  .modal label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-muted); }
  .modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 4px; }
  .toast { position: fixed; bottom: 24px; right: 24px; background: var(--accent); color: #fff; padding: 10px 16px; border-radius: var(--r-md); font-size: 13px; z-index: 400; }
</style>
