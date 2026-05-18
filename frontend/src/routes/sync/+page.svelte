<script lang="ts">
  import { onMount } from 'svelte';
  import * as api from '$lib/api';

  // WeChat
  let wechatFolder = $state('');
  let wechatStatus = $state<api.WechatStatus | null>(null);
  let wechatChats = $state<api.WechatChat[]>([]);
  let wechatBusy = $state(false);
  let wechatErr = $state('');

  // Assign modal
  let assignChatHash = $state<string | null>(null);
  let assignVendor = $state('');
  let assignContactUuid = $state('');

  // Email
  let emailCfg = $state<api.EmailConfig>({ host: '', user: '', app_password: '', interval_minutes: 5 });
  let emailStatus = $state<api.EmailStatus | null>(null);
  let emailBusy = $state(false);
  let emailErr = $state('');

  // URL ingest
  let ingestUrlVal = $state('');
  let ingestVendor = $state('');
  let ingestBusy = $state(false);
  let ingestResult = $state<api.UrlIngestResponse | null>(null);
  let ingestErr = $state('');

  async function refreshWechat() {
    try {
      wechatStatus = await api.getWechatStatus();
      const r = await api.listWechatChats();
      wechatChats = r.chats || [];
    } catch (e) {
      wechatErr = String((e as Error).message || e);
    }
  }

  async function refreshEmail() {
    try {
      emailStatus = await api.getEmailStatus();
    } catch (e) {
      emailErr = String((e as Error).message || e);
    }
  }

  onMount(() => {
    refreshWechat();
    refreshEmail();
  });

  async function startWechat() {
    if (!wechatFolder.trim()) return;
    wechatBusy = true; wechatErr = '';
    try {
      wechatStatus = await api.startWechatWatcher(wechatFolder.trim());
    } catch (e) { wechatErr = String((e as Error).message || e); }
    finally { wechatBusy = false; refreshWechat(); }
  }

  async function stopWechat() {
    wechatBusy = true;
    try { wechatStatus = await api.stopWechatWatcher(); }
    catch (e) { wechatErr = String((e as Error).message || e); }
    finally { wechatBusy = false; refreshWechat(); }
  }

  async function scanWechat() {
    if (!wechatFolder.trim()) return;
    wechatBusy = true; wechatErr = '';
    try { await api.scanWechatFolder(wechatFolder.trim()); }
    catch (e) { wechatErr = String((e as Error).message || e); }
    finally { wechatBusy = false; refreshWechat(); }
  }

  function openAssign(hash: string, currentVendor?: string) {
    assignChatHash = hash;
    assignVendor = currentVendor || '';
    assignContactUuid = '';
  }

  async function saveAssign() {
    if (!assignChatHash || !assignVendor.trim()) return;
    try {
      await api.assignWechatChat(assignChatHash, assignVendor.trim(), assignContactUuid.trim() || undefined);
      assignChatHash = null;
      await refreshWechat();
    } catch (e) {
      wechatErr = String((e as Error).message || e);
    }
  }

  async function unassign(hash: string) {
    try { await api.deleteWechatChat(hash); await refreshWechat(); }
    catch (e) { wechatErr = String((e as Error).message || e); }
  }

  async function startEmail() {
    if (!emailCfg.host || !emailCfg.user || !emailCfg.app_password) return;
    emailBusy = true; emailErr = '';
    try { emailStatus = await api.startEmailPoll(emailCfg); }
    catch (e) { emailErr = String((e as Error).message || e); }
    finally { emailBusy = false; refreshEmail(); }
  }

  async function stopEmail() {
    emailBusy = true;
    try { emailStatus = await api.stopEmailPoll(); }
    catch (e) { emailErr = String((e as Error).message || e); }
    finally { emailBusy = false; refreshEmail(); }
  }

  async function doIngestUrl() {
    if (!ingestUrlVal.trim()) return;
    ingestBusy = true; ingestErr = ''; ingestResult = null;
    try { ingestResult = await api.ingestUrl(ingestUrlVal.trim(), ingestVendor.trim() || undefined); }
    catch (e) { ingestErr = String((e as Error).message || e); }
    finally { ingestBusy = false; }
  }
</script>

<svelte:head><title>Sync | KONTACT</title></svelte:head>

<div class="page">
  <header class="page-head">
    <h1 class="page-title">Sync</h1>
    <p class="page-sub">Desktop · email · web</p>
  </header>

  <!-- WECHAT -->
  <section class="card">
    <h2>WeChat desktop sync</h2>
    <p class="muted">Watch a WeChat Files folder, auto-ingest catalogs shared by vendors.</p>

    <div class="row">
      <input class="input" placeholder="/path/to/WeChat Files" bind:value={wechatFolder} />
      <button class="send-btn" onclick={startWechat} disabled={wechatBusy || !wechatFolder.trim()}>Start</button>
      <button class="btn-ghost" onclick={stopWechat} disabled={wechatBusy}>Stop</button>
      <button class="btn-ghost" onclick={scanWechat} disabled={wechatBusy || !wechatFolder.trim()}>Scan now</button>
    </div>

    {#if wechatErr}<p class="err">{wechatErr}</p>{/if}

    <div class="status-line">
      <span class="chip {wechatStatus?.watching ? 'chip-success' : ''}">
        {wechatStatus?.watching ? 'Watching' : 'Idle'}
      </span>
      {#if wechatStatus?.folder}<span class="mono">{wechatStatus.folder}</span>{/if}
      {#if wechatStatus?.last_sync}<span class="muted">last: {wechatStatus.last_sync}</span>{/if}
      {#if wechatStatus?.files_seen != null}<span class="muted">files: {wechatStatus.files_seen}</span>{/if}
    </div>

    <h3>Mapped chats</h3>
    {#if wechatChats.length === 0}
      <p class="muted">No chats mapped yet.</p>
    {:else}
      <div class="table-scroll">
        <table class="data-table">
          <thead><tr><th>Chat hash</th><th>Vendor</th><th>Files</th><th></th></tr></thead>
          <tbody>
            {#each wechatChats as c}
              <tr>
                <td class="uuid-cell">{c.chat_hash.slice(0, 12)}</td>
                <td>{c.vendor_company || '—'}</td>
                <td>{c.file_count}</td>
                <td class="actions-cell">
                  <button class="btn-ghost xs" onclick={() => openAssign(c.chat_hash, c.vendor_company)}>Assign</button>
                  <button class="btn-danger xs" onclick={() => unassign(c.chat_hash)}>Unassign</button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>

  <!-- EMAIL -->
  <section class="card">
    <h2>Email sync</h2>
    <p class="muted">Poll an IMAP inbox, auto-ingest attachments (PDF + images).</p>

    <div class="grid">
      <label>Host<input class="input" placeholder="imap.gmail.com" bind:value={emailCfg.host} /></label>
      <label>User<input class="input" placeholder="you@example.com" bind:value={emailCfg.user} /></label>
      <label>App password<input class="input" type="password" placeholder="••••••••" bind:value={emailCfg.app_password} /></label>
      <label>Interval (min)<input class="input" type="number" min="1" bind:value={emailCfg.interval_minutes} /></label>
    </div>

    <div class="row">
      <button class="send-btn" onclick={startEmail} disabled={emailBusy}>Start</button>
      <button class="btn-ghost" onclick={stopEmail} disabled={emailBusy}>Stop</button>
    </div>

    {#if emailErr}<p class="err">{emailErr}</p>{/if}

    <div class="status-line">
      <span class="chip {emailStatus?.polling ? 'chip-success' : ''}">
        {emailStatus?.polling ? 'Polling' : 'Idle'}
      </span>
      {#if emailStatus?.user}<span class="mono">{emailStatus.user}</span>{/if}
      {#if emailStatus?.last_poll}<span class="muted">last: {emailStatus.last_poll}</span>{/if}
      {#if emailStatus?.messages_seen != null}<span class="muted">seen: {emailStatus.messages_seen}</span>{/if}
    </div>
  </section>

  <!-- URL INGEST -->
  <section class="card">
    <h2>URL ingest</h2>
    <p class="muted">Fetch a vendor product page or PDF link and ingest it.</p>

    <div class="row">
      <input class="input" placeholder="https://vendor.com/catalog.pdf" bind:value={ingestUrlVal} />
      <input class="input narrow" placeholder="vendor (optional)" bind:value={ingestVendor} />
      <button class="send-btn" onclick={doIngestUrl} disabled={ingestBusy || !ingestUrlVal.trim()}>
        {ingestBusy ? 'Fetching...' : 'Fetch'}
      </button>
    </div>

    {#if ingestErr}<p class="err">{ingestErr}</p>{/if}
    {#if ingestResult}
      <div class="result-block">
        <p><strong>{ingestResult.title || 'Ingested'}</strong></p>
        {#if ingestResult.document_uuid}<p class="mono">UUID: {ingestResult.document_uuid}</p>{/if}
        {#if ingestResult.preview}<pre class="preview">{ingestResult.preview}</pre>{/if}
        <p class="muted">{ingestResult.message}</p>
      </div>
    {/if}
  </section>
</div>

<!-- ASSIGN MODAL -->
{#if assignChatHash}
  <div class="modal-backdrop" onclick={() => assignChatHash = null} role="button" tabindex="-1" onkeydown={(e) => e.key === 'Escape' && (assignChatHash = null)}>
    <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog">
      <div class="modal-head">
        <h3>Assign chat</h3>
        <button class="modal-close" onclick={() => assignChatHash = null} aria-label="close">&times;</button>
      </div>
      <p class="mono small">{assignChatHash}</p>
      <label>Vendor company
        <input class="input" bind:value={assignVendor} placeholder="e.g. Ahua Industrial" />
      </label>
      <label>Contact UUID (optional)
        <input class="input" bind:value={assignContactUuid} placeholder="paste contact uuid" />
      </label>
      <div class="modal-actions">
        <button class="btn-ghost" onclick={() => assignChatHash = null}>Cancel</button>
        <button class="send-btn" onclick={saveAssign} disabled={!assignVendor.trim()}>Save</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .page {
    max-width: 920px;
    margin: 0 auto;
    padding: 16px 16px 64px;
    font-family: var(--font-sans);
    display: flex; flex-direction: column;
    gap: 16px;
  }
  .page-head { margin-bottom: 0; }
  .page-title { font-size: 24px; font-weight: 600; color: var(--text); margin: 0; }
  .page-sub { font-size: 14px; color: var(--text-muted); margin: 4px 0 0; }

  .card {
    display: flex; flex-direction: column;
    gap: 12px;
  }
  .card h2 { margin: 0; font-size: 18px; font-weight: 600; color: var(--text); }
  .card h3 {
    margin: 12px 0 4px;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-muted);
  }

  .muted { color: var(--text-muted); font-size: 13px; margin: 0; }
  .err { color: var(--danger); font-size: 13px; margin: 0; }
  .mono { font-family: var(--font-mono); font-size: 12px; word-break: break-all; color: var(--text-muted); }
  .small { font-size: 12px; }

  .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .grid label {
    display: flex; flex-direction: column; gap: 4px;
    font-size: 12px; font-weight: 500;
    color: var(--text-muted);
  }
  @media (max-width: 600px) { .grid { grid-template-columns: 1fr; } }

  .input { flex: 1; min-width: 0; }
  .input.narrow { max-width: 200px; flex: 0 0 auto; }

  .status-line {
    display: flex; gap: 8px; flex-wrap: wrap;
    align-items: center; font-size: 13px;
  }
  .chip-success {
    background: rgba(90,143,61,0.15);
    color: var(--success);
  }

  .table-scroll {
    overflow-x: auto;
    max-height: 360px;
    border: 1px solid var(--border);
    border-radius: var(--r-md);
  }
  .data-table {
    width: 100%; border-collapse: collapse;
    font-size: 13px; min-width: 460px;
  }
  .data-table thead tr {
    background: var(--surface-2);
    position: sticky; top: 0;
  }
  .data-table th {
    padding: 10px 12px;
    font-size: 12px;
    font-weight: 500;
    color: var(--text-muted);
    text-align: left;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }
  .data-table td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    color: var(--text);
  }
  .data-table tbody tr:hover { background: var(--surface-2); }
  .data-table tbody tr:last-child td { border-bottom: none; }

  .uuid-cell { font-family: var(--font-mono); color: var(--text-muted); font-size: 12px; }
  .actions-cell { white-space: nowrap; }
  .btn-ghost.xs, .btn-danger.xs {
    padding: 4px 10px;
    font-size: 11px;
    min-height: 24px;
    margin-right: 4px;
  }

  .result-block {
    padding: 12px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--r-md);
    margin-top: 6px;
  }
  .result-block p { margin: 0 0 4px; font-size: 13px; }
  .preview {
    font-family: var(--font-mono);
    font-size: 12px;
    max-height: 180px;
    overflow: auto;
    margin: 6px 0;
    white-space: pre-wrap;
    color: var(--text);
  }

  /* Modal */
  .modal-backdrop {
    position: fixed; inset: 0;
    background: rgba(44, 43, 38, 0.4);
    backdrop-filter: blur(2px);
    -webkit-backdrop-filter: blur(2px);
    display: flex; align-items: center; justify-content: center;
    z-index: 200; padding: 16px;
  }
  .modal {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    box-shadow: var(--shadow-lg);
    padding: 20px;
    width: 100%; max-width: 480px;
    display: flex; flex-direction: column;
    gap: 12px;
  }
  .modal-head { display: flex; justify-content: space-between; align-items: center; }
  .modal h3 { margin: 0; font-size: 16px; font-weight: 600; }
  .modal-close {
    background: none; border: none;
    font-size: 22px; line-height: 1; cursor: pointer;
    color: var(--text-muted); padding: 0 4px;
  }
  .modal-close:hover { color: var(--text); }
  .modal label {
    display: flex; flex-direction: column; gap: 4px;
    font-size: 12px; font-weight: 500;
    color: var(--text-muted);
  }
  .modal-actions {
    display: flex; gap: 8px; justify-content: flex-end;
    margin-top: 4px;
  }
</style>
