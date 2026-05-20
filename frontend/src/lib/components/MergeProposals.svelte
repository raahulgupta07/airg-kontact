<script lang="ts">
  let proposals = $state<any[]>([]);
  let loading = $state(false);
  let scanning = $state(false);
  let entityFilter = $state<'all' | 'contact' | 'document'>('all');
  let minConf = $state(0);
  let toastMsg = $state('');

  function toast(m: string) { toastMsg = m; setTimeout(() => toastMsg = '', 2400); }

  async function loadProposals() {
    loading = true;
    try {
      const qs = new URLSearchParams({
        status: 'pending',
        min_confidence: String(minConf),
        limit: '500',
      });
      if (entityFilter !== 'all') qs.set('entity', entityFilter);
      const r = await fetch(`/api/merge/proposals?${qs}`, { credentials: 'include' });
      if (r.ok) proposals = await r.json();
      else if (r.status === 403) toast('Admin required');
      else toast('Load failed: ' + r.status);
    } catch (e: any) {
      toast('Load error: ' + e.message);
    } finally {
      loading = false;
    }
  }

  async function runScan() {
    scanning = true;
    try {
      const r = await fetch('/api/merge/scan', { method: 'POST', credentials: 'include' });
      if (r.ok) {
        const res = await r.json();
        const ct = Object.values(res.contacts || {}).reduce((a: number, b: any) => a + b, 0);
        const dc = Object.values(res.documents || {}).reduce((a: number, b: any) => a + b, 0);
        toast(`Scan found ${ct} contact + ${dc} document proposals`);
        await loadProposals();
      } else {
        toast('Scan failed: ' + r.status);
      }
    } finally {
      scanning = false;
    }
  }

  async function approve(uuid: string) {
    const r = await fetch(`/api/merge/proposals/${uuid}/approve`, { method: 'POST', credentials: 'include' });
    if (r.ok) { toast('Merged'); proposals = proposals.filter(p => p.uuid !== uuid); }
    else toast('Approve failed: ' + r.status);
  }

  async function reject(uuid: string) {
    const r = await fetch(`/api/merge/proposals/${uuid}/reject`, { method: 'POST', credentials: 'include' });
    if (r.ok) { toast('Rejected'); proposals = proposals.filter(p => p.uuid !== uuid); }
    else toast('Reject failed: ' + r.status);
  }

  async function swap(uuid: string) {
    const r = await fetch(`/api/merge/proposals/${uuid}/swap`, { method: 'POST', credentials: 'include' });
    if (r.ok) { toast('Swapped'); await loadProposals(); }
  }

  async function bulkApprove() {
    if (!confirm(`Approve all proposals ≥ ${(minConf * 100).toFixed(0)}% confidence?`)) return;
    const r = await fetch('/api/merge/proposals/bulk-approve', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ min_confidence: Math.max(minConf, 0.95), entity: entityFilter === 'all' ? null : entityFilter }),
    });
    if (r.ok) {
      const j = await r.json();
      toast(`Approved ${j.approved}, errors ${j.errors.length}`);
      await loadProposals();
    }
  }

  function parseSnap(json: string): any {
    try { return JSON.parse(json || '{}'); } catch { return {}; }
  }

  function fieldsForEntity(entity: string): string[] {
    if (entity === 'contact') return ['company', 'person', 'phone_e164', 'email', 'website', 'address'];
    return ['company', 'source_file', 'image_type', 'image_phash', 'file_hash', 'trade_show'];
  }

  $effect(() => {
    void entityFilter; void minConf;
    loadProposals();
  });
</script>

<div class="card">
  <div class="head">
    <h2>Pending Merges <span class="muted">({proposals.length})</span></h2>
    <div class="controls">
      <select bind:value={entityFilter}>
        <option value="all">All</option>
        <option value="contact">Contacts</option>
        <option value="document">Documents</option>
      </select>
      <label>Min conf
        <input type="number" min="0" max="1" step="0.05" bind:value={minConf} />
      </label>
      <button class="btn-ghost xs" onclick={runScan} disabled={scanning}>{scanning ? '⏳ Scanning…' : '🔍 Scan now'}</button>
      <button class="btn-primary xs" onclick={bulkApprove} disabled={proposals.length === 0}>✓ Bulk approve ≥0.95</button>
    </div>
  </div>

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if proposals.length === 0}
    <p class="muted">No pending proposals. Click "Scan now" to find duplicates.</p>
  {:else}
    <div class="proposals">
      {#each proposals as p (p.uuid)}
        {@const beforeSnap = parseSnap(p.before_snapshot)}
        <div class="prop-card">
          <div class="prop-head">
            <span class="chip chip-{p.entity_type}">{p.entity_type}</span>
            <span class="reason">{p.match_reason}</span>
            <div class="conf-bar"><div class="conf-fill" style="width: {p.confidence * 100}%"></div></div>
            <span class="conf-num">{(p.confidence * 100).toFixed(0)}%</span>
            <span class="muted">{new Date(p.created_at).toLocaleString()}</span>
          </div>

          <div class="diff">
            <div class="side keep">
              <h4>✓ KEEP <code>{p.keep_uuid.slice(0,8)}</code></h4>
              <p class="muted small">Master record. Will absorb data from drop record.</p>
            </div>
            <div class="side drop">
              <h4>✕ DROP <code>{p.drop_uuid.slice(0,8)}</code></h4>
              <dl>
                {#each fieldsForEntity(p.entity_type) as f}
                  <dt>{f}</dt><dd>{beforeSnap[f] ?? '—'}</dd>
                {/each}
              </dl>
            </div>
          </div>

          <div class="actions">
            <button class="btn-primary" onclick={() => approve(p.uuid)}>✓ Approve</button>
            <button class="btn-ghost" onclick={() => reject(p.uuid)}>✕ Reject</button>
            <button class="btn-ghost" onclick={() => swap(p.uuid)}>⇄ Swap keep/drop</button>
          </div>
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
  .controls select, .controls input { padding: 6px 8px; border: 1px solid var(--border); border-radius: var(--r-sm); background: var(--surface); color: var(--text); font-size: 13px; }
  .controls input[type="number"] { width: 70px; }
  .controls label { display: flex; gap: 4px; align-items: center; font-size: 12px; color: var(--text-muted); }
  .muted { color: var(--text-muted); font-size: 13px; }

  .proposals { display: flex; flex-direction: column; gap: 12px; }
  .prop-card { border: 1px solid var(--border); border-radius: var(--r-md); padding: 12px; background: var(--surface-2, var(--surface)); }
  .prop-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 12px; flex-wrap: wrap; }
  .chip { padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }
  .chip-contact { background: rgba(70, 130, 200, 0.15); color: #4682c8; }
  .chip-document { background: rgba(201, 100, 66, 0.15); color: var(--accent, #c96442); }
  .reason { font-family: monospace; color: var(--text); }
  .conf-bar { flex: 1; max-width: 200px; height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
  .conf-fill { height: 100%; background: var(--accent, #c96442); }
  .conf-num { font-weight: 600; font-size: 12px; }

  .diff { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
  .side { padding: 8px; border: 1px solid var(--border); border-radius: var(--r-sm); }
  .side.keep { background: rgba(80, 180, 100, 0.05); border-color: rgba(80, 180, 100, 0.3); }
  .side.drop { background: rgba(200, 80, 80, 0.05); border-color: rgba(200, 80, 80, 0.3); }
  .side h4 { margin: 0 0 6px; font-size: 12px; font-weight: 700; }
  .side code { font-size: 10px; color: var(--text-muted); margin-left: 4px; }
  .side dl { margin: 0; display: grid; grid-template-columns: max-content 1fr; gap: 2px 8px; font-size: 12px; }
  .side dt { color: var(--text-muted); font-weight: 500; }
  .side dd { margin: 0; word-break: break-word; }

  .actions { display: flex; gap: 8px; }
  .btn-primary, .btn-ghost { padding: 6px 12px; border-radius: var(--r-sm); font-size: 13px; cursor: pointer; font-family: inherit; }
  .btn-primary { background: var(--accent, #c96442); color: white; border: 1px solid var(--accent, #c96442); font-weight: 600; }
  .btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text); }
  .btn-primary.xs, .btn-ghost.xs { padding: 5px 10px; font-size: 12px; }

  .toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: var(--surface); border: 1px solid var(--border); padding: 10px 16px; border-radius: var(--r-md); box-shadow: 0 4px 16px rgba(0,0,0,0.15); z-index: 1000; }
</style>
