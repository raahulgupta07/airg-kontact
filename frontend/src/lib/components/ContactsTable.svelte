<script>
  import * as api from '$lib/api';
  import { shortDate, relativeDate } from '$lib/utils';
  let { contacts = [], onEdit = (_c) => {}, onMerge = (_uuid) => {} } = $props();

  let contactSearch = $state('');
  let toastMsg = $state('');
  function showToast(m) { toastMsg = m; setTimeout(() => toastMsg = '', 2400); }

  async function doDownloadVcard(uuid) {
    try { await api.downloadVcard(uuid); }
    catch (e) { showToast('vCard failed: ' + e.message); }
  }
  async function downloadAllVcards() {
    try { await api.downloadAllVcardsZip(); }
    catch (e) { showToast('Bulk vCard failed: ' + e.message); }
  }

  let filteredContacts = $derived.by(() => {
    if (!contactSearch.trim()) return contacts;
    const q = contactSearch.toLowerCase();
    return contacts.filter(c =>
      (c.company || '').toLowerCase().includes(q) ||
      (c.person || c.name || '').toLowerCase().includes(q) ||
      (c.phone || c.phone_e164 || '').toLowerCase().includes(q) ||
      (c.email || '').toLowerCase().includes(q) ||
      (c.website || '').toLowerCase().includes(q) ||
      (c.address || '').toLowerCase().includes(q) ||
      (c.owner_name || '').toLowerCase().includes(q) ||
      (c.source_channel || '').toLowerCase().includes(q) ||
      (c.backfill_source || '').toLowerCase().includes(q) ||
      (c.uuid || '').toLowerCase().includes(q)
    );
  });
</script>

<div class="card table-card">
  <div class="table-head">
    <h2>Contacts</h2>
    <button class="send-btn" onclick={downloadAllVcards}>Download all .vcf (zip)</button>
  </div>
  <div class="table-toolbar">
    <input type="text" class="input" placeholder="Filter contacts..." bind:value={contactSearch} />
  </div>
  {#if contacts.length === 0}
    <p class="muted">Loading contacts...</p>
  {:else}
    <div class="table-scroll">
      <table class="data-table">
        <thead>
          <tr><th>UUID</th><th>Company</th><th>Person</th><th>Phone</th><th>Email</th><th>Website</th><th>Created</th><th>Updated</th><th>Owner</th><th>Source</th><th></th></tr>
        </thead>
        <tbody>
          {#each filteredContacts as c}
            <tr>
              <td class="uuid-cell">{(c.uuid || '').slice(0, 8)}</td>
              <td>
                {c.company || ''}
                {#if c.backfill_source && c.company}
                  <span class="bf-chip" title="Auto-filled by backfill: {c.backfill_source}">↻ {c.backfill_source}</span>
                {/if}
              </td>
              <td>{c.person || c.name || c.contact_name || ''}</td>
              <td>{c.phone || c.telephone || ''}</td>
              <td>{c.email || ''}</td>
              <td>{c.website || c.url || ''}</td>
              <td class="date-cell">{shortDate(c.created_at)}</td>
              <td class="date-cell">{relativeDate(c.updated_at)}</td>
              <td class="owner-cell">{c.owner_name || ''}</td>
              <td>{#if c.source_channel}<span class="src-chip src-{c.source_channel}">{c.source_channel}</span>{/if}</td>
              <td class="actions-cell">
                <button class="btn-ghost xs" onclick={() => onEdit(c)}>Edit</button>
                <button class="btn-ghost xs" onclick={() => doDownloadVcard(c.uuid)} disabled={!c.uuid}>.vcf</button>
                <button class="btn-ghost xs" onclick={() => onMerge(c.uuid)} disabled={!c.uuid}>Merge</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

{#if toastMsg}<div class="toast">{toastMsg}</div>{/if}

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 16px; }
  .card h2 { margin: 0 0 8px; font-size: 16px; font-weight: 600; color: var(--text); }
  .muted { color: var(--text-muted); font-size: 13px; }
  .table-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
  .table-toolbar { display: flex; align-items: center; gap: 8px; margin: 8px 0 12px; flex-wrap: wrap; }
  .table-toolbar .input { flex: 1; min-width: 160px; }
  .table-scroll { overflow: auto; max-height: 560px; -webkit-overflow-scrolling: touch; border: 1px solid var(--border); border-radius: var(--r-md); }
  .data-table { width: 100%; border-collapse: collapse; font-family: var(--font-sans); font-size: 13px; min-width: 500px; }
  .data-table thead tr { background: var(--surface-2); }
  .data-table th { padding: 10px 12px; font-size: 12px; font-weight: 500; color: var(--text-muted); text-align: left; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--surface-2); z-index: 2; white-space: nowrap; }
  .data-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--text); vertical-align: top; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .data-table tbody tr:hover { background: var(--surface-2); }
  .data-table tbody tr:last-child td { border-bottom: none; }
  .uuid-cell { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); max-width: 80px; }
  .date-cell { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
  .owner-cell { font-size: 12px; color: var(--text-muted); max-width: 140px; }
  .src-chip {
    font-size: 10px;
    padding: 2px 6px;
    border-radius: var(--r-pill);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 600;
  }
  .src-upload { background: var(--accent-soft); color: var(--accent); }
  .src-wechat { background: rgba(7,193,96,0.1); color: #07c160; }
  .src-email { background: rgba(66,133,244,0.1); color: #4285f4; }
  .src-url { background: rgba(155,89,182,0.1); color: #9b59b6; }
  .bf-chip {
    display: inline-block;
    margin-left: 6px;
    padding: 1px 6px;
    border-radius: var(--r-pill);
    font-size: 10px;
    background: rgba(160, 160, 160, 0.15);
    color: var(--text-muted);
    font-weight: 500;
  }
  .src-api { background: var(--surface-2); color: var(--text-muted); }
  .actions-cell { white-space: nowrap; }
  .btn-ghost.xs { padding: 4px 10px; font-size: 11px; min-height: 24px; margin-right: 4px; }
  .toast { position: fixed; bottom: 24px; right: 24px; background: var(--accent); color: #fff; padding: 10px 16px; font-size: 13px; font-weight: 500; border-radius: var(--r-md); box-shadow: var(--shadow-md); z-index: 400; }
</style>
