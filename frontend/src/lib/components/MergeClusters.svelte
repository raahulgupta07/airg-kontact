<script lang="ts">
  let clusters = $state<any[]>([]);
  let loading = $state(false);
  let scanning = $state(false);
  let entityFilter = $state<'all' | 'contact' | 'document'>('all');
  let reasonFilter = $state<'all' | string>('all');
  let minConf = $state(0);
  let toastMsg = $state('');
  let expanded = $state<Record<string, boolean>>({});
  let busyKey = $state<Record<string, boolean>>({});

  function toast(m: string) { toastMsg = m; setTimeout(() => toastMsg = '', 3500); }

  function cKey(c: any): string { return `${c.keep_uuid}|${c.match_reason}`; }

  async function load() {
    loading = true;
    try {
      const qs = new URLSearchParams({ status: 'pending', min_confidence: String(minConf), limit: '200' });
      if (entityFilter !== 'all') qs.set('entity', entityFilter);
      const r = await fetch(`/api/merge/clusters?${qs}`, { credentials: 'include' });
      if (r.ok) clusters = await r.json();
      else toast('Load failed: ' + r.status);
    } finally { loading = false; }
  }

  async function runScan() {
    scanning = true;
    try {
      const r = await fetch('/api/merge/scan', { method: 'POST', credentials: 'include' });
      if (r.ok) {
        const res = await r.json();
        const tot = Object.values(res.contacts || {}).reduce((a: number, b: any) => a + b, 0) +
                    Object.values(res.documents || {}).reduce((a: number, b: any) => a + b, 0);
        toast(`Scan: ${tot} new proposals`);
        await load();
      }
    } finally { scanning = false; }
  }

  async function approveCluster(c: any) {
    const k = cKey(c);
    if (!confirm(`Merge ${c.drop_count} duplicate(s) into "${c.keep_preview?.company || c.keep_preview?.source_file || c.keep_uuid.slice(0,8)}"?\n\nKeeps the master, drops ${c.drop_count} duplicate(s).`)) return;
    busyKey = { ...busyKey, [k]: true };
    try {
      const r = await fetch('/api/merge/clusters/approve', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keep_uuid: c.keep_uuid, match_reason: c.match_reason, entity_type: c.entity_type }),
      });
      const body = await r.json();
      if (r.ok) {
        toast(`✓ Merged ${body.approved} record(s)${body.errors?.length ? ', errors '+body.errors.length : ''}`);
        clusters = clusters.filter(x => cKey(x) !== k);
      } else { toast('Approve failed: ' + (body.detail || r.status)); }
    } finally { busyKey = { ...busyKey, [k]: false }; }
  }

  async function rejectCluster(c: any) {
    const k = cKey(c);
    if (!confirm(`Reject all ${c.drop_count} merge(s) in this cluster?\nThe pairs go into the blacklist and won't be re-proposed.`)) return;
    busyKey = { ...busyKey, [k]: true };
    try {
      const r = await fetch('/api/merge/clusters/reject', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keep_uuid: c.keep_uuid, match_reason: c.match_reason, entity_type: c.entity_type }),
      });
      if (r.ok) {
        const body = await r.json();
        toast(`✕ Rejected ${body.rejected}`);
        clusters = clusters.filter(x => cKey(x) !== k);
      }
    } finally { busyKey = { ...busyKey, [k]: false }; }
  }

  async function bulkApproveHighConf() {
    const eligible = clusters.filter(c => c.confidence >= 0.95);
    if (!eligible.length) { toast('Nothing ≥0.95'); return; }
    const total = eligible.reduce((s, c) => s + c.drop_count, 0);
    if (!confirm(`Bulk-approve ${eligible.length} cluster(s) = ${total} duplicate merges total. Proceed?`)) return;
    let ok = 0, err = 0;
    for (const c of eligible) {
      const r = await fetch('/api/merge/clusters/approve', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keep_uuid: c.keep_uuid, match_reason: c.match_reason, entity_type: c.entity_type }),
      });
      const body = await r.json().catch(() => ({}));
      if (r.ok) { ok += body.approved || 0; }
      else { err++; }
    }
    toast(`Bulk approved ${ok} records, ${err} cluster errors`);
    await load();
  }

  // Insights per cluster
  function clusterInsights(c: any): string[] {
    const out: string[] = [];
    const p = c.keep_preview || {};
    if (c.match_reason === 'file_hash') {
      out.push(`Byte-identical files (${c.drop_count}× duplicate uploads)`);
      const size = p.file_size_kb;
      if (size) out.push(`~${((size * c.drop_count) / 1024).toFixed(1)} MB storage saved on merge`);
    } else if (c.match_reason === 'phash_exact') {
      out.push(`Visually identical (perceptual hash ≤4 bits diff)`);
      out.push(`Likely same image at different sizes/quality`);
    } else if (c.match_reason === 'phash_near') {
      out.push(`Visually similar (5-8 bits diff) — review carefully, may be variants`);
    } else if (c.match_reason === 'filename') {
      out.push(`Same filename re-uploaded by same owner`);
      out.push(`Common when user retries without "force" flag`);
    } else if (c.match_reason === 'phone_e164') {
      out.push(`Same phone number across ${c.drop_count + 1} contacts`);
    } else if (c.match_reason === 'email') {
      out.push(`Same email across ${c.drop_count + 1} contacts`);
    } else if (c.match_reason === 'company_person') {
      out.push(`Same company + person name match`);
    }
    if (p.image_type === 'qr_card') out.push(`QR business card`);
    if (p.trade_show) out.push(`Show: ${p.trade_show}`);
    return out;
  }

  function fmtFields(snap: any, entity: string): {label: string; value: string}[] {
    if (entity === 'contact') {
      return [
        { label: 'Company', value: snap.company || '—' },
        { label: 'Person',  value: snap.person || '—' },
        { label: 'Phone',   value: snap.phone_e164 || snap.phone || '—' },
        { label: 'Email',   value: snap.email || '—' },
      ];
    }
    return [
      { label: 'Company',   value: snap.company || '—' },
      { label: 'File',      value: snap.source_file || '—' },
      { label: 'Type',      value: snap.image_type || '—' },
      { label: 'Trade show', value: snap.trade_show || '—' },
    ];
  }

  $effect(() => { void entityFilter; void minConf; load(); });
</script>

<div class="card">
  <div class="head">
    <h2>Duplicate Clusters <span class="muted">({clusters.length})</span></h2>
    <div class="controls">
      <select bind:value={entityFilter}>
        <option value="all">All</option>
        <option value="contact">Contacts</option>
        <option value="document">Documents</option>
      </select>
      <label>Min conf
        <input type="number" min="0" max="1" step="0.05" bind:value={minConf} />
      </label>
      <button class="btn-ghost xs" onclick={runScan} disabled={scanning}>{scanning ? '⏳' : '🔍'} Scan now</button>
      <button class="btn-primary xs" onclick={bulkApproveHighConf} disabled={clusters.length === 0}>
        ✓ Bulk approve ≥0.95
      </button>
    </div>
  </div>

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if clusters.length === 0}
    <p class="muted">No duplicate clusters. Click "Scan now" to find duplicates.</p>
  {:else}
    <div class="clusters">
      {#each clusters as c (cKey(c))}
        {@const insights = clusterInsights(c)}
        {@const keepFields = fmtFields(c.keep_preview || {}, c.entity_type)}
        {@const isDoc = c.entity_type === 'document'}
        {@const expandedKey = cKey(c)}
        <div class="cluster">
          <div class="c-head">
            <span class="chip chip-{c.entity_type}">{c.entity_type}</span>
            <span class="reason">{c.match_reason}</span>
            <span class="drop-count">{c.drop_count} duplicate{c.drop_count === 1 ? '' : 's'}</span>
            <div class="conf-bar"><div class="conf-fill" style="width: {c.confidence * 100}%"></div></div>
            <span class="conf-num">{(c.confidence * 100).toFixed(0)}%</span>
          </div>

          {#if insights.length}
            <ul class="insights">
              {#each insights as ins}<li>💡 {ins}</li>{/each}
            </ul>
          {/if}

          <div class="cluster-body">
            <div class="keep-pane">
              <div class="pane-head">
                <span class="pane-tag keep-tag">✓ KEEP (master)</span>
                <code>{c.keep_uuid.slice(0, 8)}</code>
              </div>
              {#if isDoc && c.keep_preview?.folder && c.keep_preview?.source_file}
                <div class="thumb-wrap">
                  <img
                    class="pane-thumb"
                    src="/api/thumb/{c.keep_preview.folder}/{c.keep_preview.source_file}?w=256"
                    alt={c.keep_preview.source_file}
                    loading="lazy"
                    onerror={(e) => { const t = e.currentTarget as HTMLImageElement; t.style.display = 'none'; const nx = t.nextElementSibling as HTMLElement; if (nx) nx.style.display = 'flex'; }}
                  />
                  <div class="thumb-fallback" style="display:none">📄 No preview</div>
                </div>
              {/if}
              {#if isDoc}
                <dl class="pane-fields rich">
                  <dt>File</dt><dd class="mono">{c.keep_preview?.source_file || '—'}</dd>
                  <dt>Company</dt><dd>{c.keep_preview?.company || '—'}</dd>
                  <dt>Title</dt><dd>{c.keep_preview?.title || '—'}</dd>
                  <dt>Type</dt><dd><span class="mini-chip">{c.keep_preview?.image_type || 'unknown'}</span></dd>
                  {#if c.keep_preview?.quality_score != null}
                    <dt>Quality</dt><dd>
                      <div class="qbar"><div class="qfill" style="width:{(c.keep_preview.quality_score || 0) * 100}%"></div></div>
                      <span class="qnum">{((c.keep_preview.quality_score || 0) * 100).toFixed(0)}%</span>
                      {#if c.keep_preview.needs_revision}<span class="badge-warn">needs revision</span>{/if}
                    </dd>
                  {/if}
                  <dt>Products</dt><dd>
                    <b>{c.keep_preview?.products_count || 0}</b>
                    {#if c.keep_preview?.products_summary?.length}
                      <span class="muted small">— {c.keep_preview.products_summary.filter(Boolean).slice(0,3).join(', ')}</span>
                    {/if}
                  </dd>
                  <dt>Contact</dt><dd>
                    {#if c.keep_preview?.contact_summary?.person || c.keep_preview?.contact_summary?.phone || c.keep_preview?.contact_summary?.email}
                      {c.keep_preview.contact_summary.person || ''}
                      {#if c.keep_preview.contact_summary.phone}<span class="muted small"> · {c.keep_preview.contact_summary.phone}</span>{/if}
                      {#if c.keep_preview.contact_summary.email}<span class="muted small"> · {c.keep_preview.contact_summary.email}</span>{/if}
                    {:else}—{/if}
                  </dd>
                  <dt>Trade show</dt><dd>{c.keep_preview?.trade_show || '—'}</dd>
                  {#if c.keep_preview?.has_gps}
                    <dt>GPS</dt><dd>{c.keep_preview.city || ''} {c.keep_preview.country || ''} <span class="muted small">({c.keep_preview.gps_lat?.toFixed?.(3)}, {c.keep_preview.gps_lng?.toFixed?.(3)})</span></dd>
                  {/if}
                  {#if c.keep_preview?.date_taken}
                    <dt>Taken</dt><dd>{c.keep_preview.date_taken}</dd>
                  {/if}
                  {#if c.keep_preview?.file_size_kb}
                    <dt>Size</dt><dd>{c.keep_preview.file_size_kb.toFixed(1)} KB</dd>
                  {/if}
                  {#if c.keep_preview?.raw_text_snippet}
                    <dt>Text</dt><dd class="raw-text">{c.keep_preview.raw_text_snippet}</dd>
                  {/if}
                </dl>
              {:else}
                <dl class="pane-fields">
                  {#each keepFields as f}
                    <dt>{f.label}</dt><dd>{f.value}</dd>
                  {/each}
                </dl>
              {/if}
            </div>

            <div class="drop-pane">
              <div class="pane-head">
                <span class="pane-tag drop-tag">✕ DROP ({c.drop_count})</span>
                <button class="link-btn" onclick={() => expanded = { ...expanded, [expandedKey]: !expanded[expandedKey] }}>
                  {expanded[expandedKey] ? 'Collapse' : 'Show all'}
                </button>
              </div>

              {#if isDoc}
                <div class="drop-grid">
                  {#each (expanded[expandedKey] ? c.drops : c.drops.slice(0, 8)) as d}
                    {#if d.snapshot?.folder && d.snapshot?.source_file}
                      <div class="drop-tile" title={`${d.snapshot.source_file}\n${d.snapshot.company || ''}\n${d.snapshot.products_count || 0} product(s)\n${d.snapshot.contact_summary?.person || ''}`}>
                        <img
                          src="/api/thumb/{d.snapshot.folder}/{d.snapshot.source_file}?w=128"
                          alt={d.snapshot.source_file}
                          loading="lazy"
                          onerror={(e) => { const t = e.currentTarget as HTMLImageElement; t.style.display = 'none'; }}
                        />
                        <div class="tile-meta">
                          <span class="tile-id">{d.drop_uuid.slice(0,6)}</span>
                          <span class="tile-fname" title={d.snapshot.source_file}>{d.snapshot.source_file}</span>
                          {#if d.snapshot.products_count}
                            <span class="tile-prod">📦{d.snapshot.products_count}</span>
                          {/if}
                          {#if d.snapshot.contact_summary?.person}
                            <span class="tile-pers">👤{d.snapshot.contact_summary.person.slice(0, 12)}</span>
                          {/if}
                          {#if d.snapshot.trade_show}
                            <span class="tile-show">@{d.snapshot.trade_show.slice(0, 12)}</span>
                          {/if}
                        </div>
                      </div>
                    {/if}
                  {/each}
                  {#if !expanded[expandedKey] && c.drops.length > 8}
                    <div class="drop-more" onclick={() => expanded = { ...expanded, [expandedKey]: true }} role="button" tabindex="0">
                      +{c.drops.length - 8} more
                    </div>
                  {/if}
                </div>

                <!-- Compact data table for ALL drops -->
                {#if expanded[expandedKey]}
                  <table class="drops-table">
                    <thead>
                      <tr><th>uuid</th><th>file</th><th>company</th><th>products</th><th>contact</th><th>show</th><th>quality</th></tr>
                    </thead>
                    <tbody>
                      {#each c.drops as d}
                        <tr>
                          <td class="mono">{d.drop_uuid.slice(0,8)}</td>
                          <td class="mono small" title={d.snapshot?.source_file}>{(d.snapshot?.source_file || '').slice(0,24)}</td>
                          <td>{d.snapshot?.company || '—'}</td>
                          <td>{d.snapshot?.products_count || 0}</td>
                          <td class="small">{d.snapshot?.contact_summary?.person || '—'}</td>
                          <td class="small">{d.snapshot?.trade_show || '—'}</td>
                          <td class="small">{d.snapshot?.quality_score != null ? ((d.snapshot.quality_score * 100).toFixed(0) + '%') : '—'}</td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                {/if}
              {:else}
                <div class="contact-drops">
                  {#each (expanded[expandedKey] ? c.drops : c.drops.slice(0, 5)) as d}
                    {@const fields = fmtFields(d.snapshot || {}, c.entity_type)}
                    <div class="contact-drop">
                      <code>{d.drop_uuid.slice(0,8)}</code>
                      {#each fields as f}
                        <span class="cd-field"><b>{f.label}:</b> {f.value}</span>
                      {/each}
                    </div>
                  {/each}
                  {#if !expanded[expandedKey] && c.drops.length > 5}
                    <button class="link-btn" onclick={() => expanded = { ...expanded, [expandedKey]: true }}>
                      Show {c.drops.length - 5} more
                    </button>
                  {/if}
                </div>
              {/if}
            </div>
          </div>

          <div class="actions">
            <button class="btn-primary" disabled={busyKey[expandedKey]} onclick={() => approveCluster(c)}>
              {busyKey[expandedKey] ? '⏳ Merging…' : `✓ Merge all ${c.drop_count} into master`}
            </button>
            <button class="btn-ghost" disabled={busyKey[expandedKey]} onclick={() => rejectCluster(c)}>✕ Reject cluster</button>
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
  .controls select, .controls input { padding: 6px 8px; border: 1px solid var(--border); border-radius: var(--r-sm); background: var(--surface); color: var(--text); font-size: 13px; font-family: inherit; }
  .controls input[type="number"] { width: 70px; }
  .controls label { display: flex; gap: 4px; align-items: center; font-size: 12px; color: var(--text-muted); }
  .muted { color: var(--text-muted); font-size: 13px; }

  .clusters { display: flex; flex-direction: column; gap: 16px; }
  .cluster { border: 1px solid var(--border); border-radius: var(--r-md); padding: 14px; background: var(--surface-2, var(--surface)); }
  .c-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
  .chip { padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }
  .chip-document { background: rgba(201,100,66,0.15); color: #c96442; }
  .chip-contact  { background: rgba(70,130,200,0.15); color: #4682c8; }
  .reason { font-family: var(--font-mono); font-size: 12px; padding: 2px 6px; background: var(--surface); border-radius: 4px; }
  .drop-count { font-size: 13px; font-weight: 700; color: var(--accent); }
  .conf-bar { flex: 1; max-width: 200px; height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
  .conf-fill { height: 100%; background: var(--accent, #c96442); }
  .conf-num { font-size: 12px; font-weight: 600; min-width: 36px; text-align: right; }

  .insights { margin: 0 0 12px; padding: 8px 12px; background: rgba(80,180,100,0.06); border-left: 3px solid rgba(80,180,100,0.4); border-radius: 4px; font-size: 12px; }
  .insights li { list-style: none; color: var(--text); padding: 2px 0; }

  .cluster-body { display: grid; grid-template-columns: 280px 1fr; gap: 16px; margin-bottom: 12px; }
  .keep-pane, .drop-pane { padding: 10px; border: 1px solid var(--border); border-radius: var(--r-sm); background: var(--surface); }
  .keep-pane { background: rgba(80,180,100,0.05); border-color: rgba(80,180,100,0.3); }
  .drop-pane { background: rgba(200,80,80,0.04); border-color: rgba(200,80,80,0.25); }
  .pane-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
  .pane-tag { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; }
  .keep-tag { background: rgba(80,180,100,0.2); color: #2a8c4a; }
  .drop-tag { background: rgba(200,80,80,0.18); color: #b03030; }
  .pane-head code { font-size: 10px; color: var(--text-muted); }

  .pane-thumb { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 4px; margin-bottom: 8px; background: var(--surface-2); }
  .pane-fields { display: grid; grid-template-columns: max-content 1fr; gap: 3px 8px; margin: 0; font-size: 12px; }
  .pane-fields dt { color: var(--text-muted); font-weight: 500; }
  .pane-fields dd { margin: 0; word-break: break-word; }

  .drop-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; }
  .drop-tile {
    position: relative; aspect-ratio: 1; border: 1px solid var(--border);
    border-radius: 6px; overflow: hidden; background: var(--surface-2);
  }
  .drop-tile img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .drop-more {
    aspect-ratio: 1; display: flex; align-items: center; justify-content: center;
    border: 1px dashed var(--border); border-radius: 4px; font-size: 12px; color: var(--text-muted);
    cursor: pointer;
  }
  .drop-more:hover { background: var(--surface-2); }

  .contact-drops { display: flex; flex-direction: column; gap: 4px; max-height: 240px; overflow-y: auto; }
  .contact-drop { padding: 4px 6px; background: var(--surface); border: 1px solid var(--border); border-radius: 4px; font-size: 11px; display: flex; flex-wrap: wrap; gap: 8px; }
  .contact-drop code { font-family: var(--font-mono); color: var(--text-muted); }
  .cd-field b { font-weight: 600; color: var(--text-muted); margin-right: 2px; }
  .link-btn { background: none; border: none; color: var(--accent); cursor: pointer; font-size: 12px; font-family: inherit; padding: 0; text-decoration: underline; }

  .actions { display: flex; gap: 8px; padding-top: 10px; border-top: 1px solid var(--border); }
  .btn-primary, .btn-ghost { padding: 8px 14px; border-radius: var(--r-sm); cursor: pointer; font-family: inherit; font-size: 13px; }
  .btn-primary { background: var(--accent, #c96442); color: white; border: 1px solid var(--accent, #c96442); font-weight: 600; }
  .btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text); }
  .btn-primary:disabled, .btn-ghost:disabled { opacity: 0.6; cursor: not-allowed; }
  .btn-primary.xs, .btn-ghost.xs { padding: 5px 10px; font-size: 12px; }

  .toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: var(--surface); border: 1px solid var(--accent); padding: 10px 16px; border-radius: var(--r-md); box-shadow: 0 4px 16px rgba(0,0,0,0.18); z-index: 1000; font-size: 13px; }

  .thumb-wrap { position: relative; }
  .thumb-fallback {
    width: 100%; aspect-ratio: 1; align-items: center; justify-content: center;
    color: var(--text-muted); font-size: 12px; background: var(--surface-2);
    border-radius: 4px; margin-bottom: 8px;
  }
  .pane-fields.rich dt { font-size: 11px; padding-top: 3px; }
  .pane-fields.rich dd { font-size: 12px; line-height: 1.4; }
  .pane-fields.rich .mono { font-family: var(--font-mono); font-size: 11px; }
  .pane-fields .raw-text { font-size: 11px; color: var(--text-muted); font-style: italic; max-height: 60px; overflow: hidden; }
  .mini-chip { padding: 1px 6px; background: var(--accent-soft, rgba(201,100,66,0.12)); color: var(--accent); border-radius: 999px; font-size: 10px; }
  .qbar { display: inline-block; width: 60px; height: 5px; background: var(--border); border-radius: 3px; overflow: hidden; vertical-align: middle; }
  .qfill { height: 100%; background: var(--accent); }
  .qnum { font-size: 11px; font-weight: 600; margin-left: 4px; }
  .badge-warn { padding: 1px 5px; background: rgba(224,168,0,0.15); color: #b08800; font-size: 9px; border-radius: 3px; margin-left: 4px; }
  .small { font-size: 11px; }

  .tile-meta {
    position: absolute; left: 0; right: 0; bottom: 0;
    background: linear-gradient(to top, rgba(0,0,0,0.75), rgba(0,0,0,0.5) 70%, transparent);
    color: white; padding: 4px 4px 3px; display: flex; flex-direction: column; gap: 1px;
  }
  .tile-meta span { font-size: 9px; line-height: 1.2; }
  .tile-meta .tile-id { font-family: var(--font-mono); opacity: 0.8; }
  .tile-meta .tile-fname { font-family: var(--font-mono); font-size: 8px; opacity: 0.7; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tile-meta .tile-prod, .tile-meta .tile-pers, .tile-meta .tile-show { font-weight: 600; }

  .drops-table { width: 100%; border-collapse: collapse; font-size: 11px; margin-top: 10px; }
  .drops-table th, .drops-table td { padding: 4px 6px; border-bottom: 1px solid var(--border); text-align: left; }
  .drops-table th { color: var(--text-muted); font-weight: 600; }
  .drops-table .mono { font-family: var(--font-mono); }

  @media (max-width: 720px) {
    .cluster-body { grid-template-columns: 1fr; }
  }
</style>
