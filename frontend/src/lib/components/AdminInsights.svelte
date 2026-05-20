<script lang="ts">
  import { onMount } from 'svelte';

  let days = $state(30);
  let cost = $state<any>(null);
  let heatmap = $state<any>(null);
  let funnel = $state<any>(null);
  let loading = $state(false);

  // ── admin job runner + scheduler ────────────────
  let jobs = $state<{ id: string; label: string }[]>([]);
  let jobBusy = $state<Record<string, boolean>>({});
  let jobResults = $state<Record<string, any>>({});
  let jobToast = $state('');
  let isSuperAdmin = $state(false);
  let schedule = $state<any[]>([]);
  let editingSched = $state<Record<string, any>>({});
  let savingSched = $state<Record<string, boolean>>({});

  async function loadJobs() {
    try {
      const r = await fetch('/api/admin/jobs', { credentials: 'include' });
      if (r.ok) { jobs = (await r.json()).jobs || []; isSuperAdmin = true; }
      else { isSuperAdmin = false; return; }
      const s = await fetch('/api/admin/jobs/schedule', { credentials: 'include' });
      if (s.ok) {
        const body = await s.json();
        schedule = body.jobs || [];
        for (const j of schedule) editingSched[j.job_id] = { ...j };
      }
    } catch { isSuperAdmin = false; }
  }

  async function saveSchedule(job_id: string) {
    const e = editingSched[job_id];
    savingSched = { ...savingSched, [job_id]: true };
    try {
      const r = await fetch(`/api/admin/jobs/schedule/${job_id}`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cron_hour: e.cron_hour === '' || e.cron_hour === null ? null : Number(e.cron_hour),
          cron_minute: Number(e.cron_minute || 0),
          interval_hours: e.interval_hours === '' || e.interval_hours === null ? null : Number(e.interval_hours),
          enabled: !!e.enabled,
        }),
      });
      if (r.ok) {
        jobToast = `✓ Schedule updated for ${job_id}`;
        const body = await r.json();
        schedule = schedule.map(s => s.job_id === job_id ? body : s);
      } else {
        const body = await r.json().catch(() => ({}));
        jobToast = `✗ ${body.detail || r.status}`;
      }
    } catch (e: any) {
      jobToast = `✗ ${e.message}`;
    } finally {
      savingSched = { ...savingSched, [job_id]: false };
      setTimeout(() => jobToast = '', 4000);
    }
  }

  function fmtSchedule(s: any): string {
    if (!s.enabled) return 'disabled';
    if (s.interval_hours) return `every ${s.interval_hours}h`;
    if (s.cron_hour != null) {
      const hh = String(s.cron_hour).padStart(2, '0');
      const mm = String(s.cron_minute || 0).padStart(2, '0');
      return `daily ${hh}:${mm}`;
    }
    return 'no schedule';
  }

  async function runJob(id: string) {
    if (!confirm(`Run "${id}" now? Heavy jobs may take 1-5 min.`)) return;
    jobBusy = { ...jobBusy, [id]: true };
    jobToast = '';
    try {
      const r = await fetch(`/api/admin/jobs/run/${id}`, { method: 'POST', credentials: 'include' });
      const body = await r.json().catch(() => ({}));
      if (r.ok) {
        jobResults = { ...jobResults, [id]: body };
        jobToast = `✓ ${id} done in ${body.elapsed_sec}s`;
        load();
      } else {
        jobToast = `✗ ${id}: ${body.detail || r.status}`;
      }
    } catch (e: any) {
      jobToast = `✗ ${id}: ${e.message}`;
    } finally {
      jobBusy = { ...jobBusy, [id]: false };
      setTimeout(() => jobToast = '', 6000);
    }
  }

  async function load() {
    loading = true;
    try {
      const [c, h, f] = await Promise.all([
        fetch(`/api/admin/llm-cost?days=${days}`, { credentials: 'include' }).then(r => r.ok ? r.json() : null),
        fetch(`/api/admin/usage-heatmap?days=14`, { credentials: 'include' }).then(r => r.ok ? r.json() : null),
        fetch(`/api/admin/funnel?days=${days}`, { credentials: 'include' }).then(r => r.ok ? r.json() : null),
      ]);
      cost = c; heatmap = h; funnel = f;
    } finally {
      loading = false;
    }
  }

  function fmt(n: number, d = 2): string {
    return (n || 0).toFixed(d);
  }
  function fmtInt(n: number): string {
    return (n || 0).toLocaleString();
  }

  // Heatmap: build 14x24 grid
  let heatmapGrid = $derived.by(() => {
    if (!heatmap?.cells) return [];
    const grid: Record<string, number> = {};
    let max = 0;
    for (const c of heatmap.cells) {
      grid[`${c.day}_${c.hour}`] = c.n;
      if (c.n > max) max = c.n;
    }
    const today = new Date();
    const days: any[] = [];
    for (let i = 13; i >= 0; i--) {
      const d = new Date(today); d.setDate(d.getDate() - i);
      const dayStr = d.toISOString().slice(0, 10);
      const row = { day: dayStr, hours: [] as any[] };
      for (let h = 0; h < 24; h++) {
        const hh = String(h).padStart(2, '0');
        const n = grid[`${dayStr}_${hh}`] || 0;
        row.hours.push({ h, n, intensity: max ? n / max : 0 });
      }
      days.push(row);
    }
    return days;
  });

  onMount(() => { load(); loadJobs(); });
  $effect(() => { void days; load(); });
</script>

<div class="card">
  <div class="head">
    <h2>Admin Insights</h2>
    <select bind:value={days}>
      <option value={7}>Last 7 days</option>
      <option value={30}>Last 30 days</option>
      <option value={90}>Last 90 days</option>
    </select>
  </div>

  {#if loading}
    <p class="muted">Loading…</p>
  {/if}

  {#if isSuperAdmin && schedule.length}
    <h3 class="sub-h">🗓 Job Schedule</h3>
    <p class="muted small">Edit when each nightly job runs. Changes apply live without restart.</p>
    <div class="sched">
      {#each schedule as s (s.job_id)}
        {@const e = editingSched[s.job_id] ?? s}
        <div class="sched-row">
          <span class="sched-id">{s.job_id}</span>
          <span class="sched-cur">current: <b>{fmtSchedule(s)}</b></span>
          <label class="sw">
            <input type="checkbox" bind:checked={editingSched[s.job_id].enabled} />
            <span>{editingSched[s.job_id]?.enabled ? 'On' : 'Off'}</span>
          </label>
          <span class="sched-mode">
            {#if s.interval_hours != null}
              Every
              <input type="number" min="1" max="168" bind:value={editingSched[s.job_id].interval_hours} class="num" />
              hours
            {:else}
              Daily at
              <input type="number" min="0" max="23" bind:value={editingSched[s.job_id].cron_hour} class="num" />
              :
              <input type="number" min="0" max="59" bind:value={editingSched[s.job_id].cron_minute} class="num" />
            {/if}
          </span>
          <button class="run-btn" disabled={savingSched[s.job_id]} onclick={() => saveSchedule(s.job_id)}>
            {savingSched[s.job_id] ? '⏳' : '💾'} Save
          </button>
        </div>
      {/each}
    </div>
  {/if}

  {#if isSuperAdmin}
    <h3 class="sub-h">⚡ Run Nightly Jobs On-Demand</h3>
    <p class="muted small">Super-admin only. Manually trigger any scheduled job right now.</p>
    <div class="jobs">
      {#each jobs as job}
        <div class="job-row">
          <span class="job-id">{job.id}</span>
          <span class="job-label">{job.label}</span>
          <button class="run-btn" disabled={jobBusy[job.id]} onclick={() => runJob(job.id)}>
            {jobBusy[job.id] ? '⏳ Running…' : '▶ Run now'}
          </button>
          {#if jobResults[job.id]}
            <span class="job-result" title={JSON.stringify(jobResults[job.id].result)}>
              ✓ {jobResults[job.id].elapsed_sec}s
            </span>
          {/if}
        </div>
      {/each}
    </div>
    {#if jobToast}<div class="job-toast">{jobToast}</div>{/if}
  {/if}

  {#if funnel}
    <h3 class="sub-h">Conversion funnel</h3>
    <div class="funnel">
      <div class="step"><div class="step-n">{fmtInt(funnel.uploaded)}</div><div class="step-l">Uploaded</div></div>
      <div class="arrow">→</div>
      <div class="step"><div class="step-n">{fmtInt(funnel.extracted)}</div><div class="step-l">Extracted</div></div>
      <div class="arrow">→</div>
      <div class="step"><div class="step-n">{fmtInt(funnel.contacts_saved)}</div><div class="step-l">Contacts</div></div>
      <div class="arrow">→</div>
      <div class="step"><div class="step-n">{fmtInt(funnel.meetings_created)}</div><div class="step-l">Meetings</div></div>
    </div>
  {/if}

  {#if cost}
    <h3 class="sub-h">LLM Cost</h3>
    <div class="cost-row">
      <div class="kpi"><div class="kpi-n">${fmt(cost.totals.cost)}</div><div class="kpi-l">Total ({days}d)</div></div>
      <div class="kpi"><div class="kpi-n">{fmtInt(cost.totals.tokens)}</div><div class="kpi-l">Tokens</div></div>
      <div class="kpi"><div class="kpi-n">{fmtInt(cost.totals.calls)}</div><div class="kpi-l">Calls</div></div>
      <div class="kpi"><div class="kpi-n">${fmt(cost.totals.cost * 30 / Math.max(days,1))}</div><div class="kpi-l">~30d projected</div></div>
    </div>
    <div class="cost-tables">
      <div class="cost-col">
        <h4>By op</h4>
        <table>
          <thead><tr><th>Op</th><th>Calls</th><th>Tokens</th><th>$</th></tr></thead>
          <tbody>
            {#each cost.by_op as r}
              <tr><td>{r.op}</td><td>{fmtInt(r.calls)}</td><td>{fmtInt(r.tokens)}</td><td>${fmt(r.cost, 4)}</td></tr>
            {/each}
          </tbody>
        </table>
      </div>
      <div class="cost-col">
        <h4>By user (top 10)</h4>
        <table>
          <thead><tr><th>User</th><th>Calls</th><th>Tokens</th><th>$</th></tr></thead>
          <tbody>
            {#each cost.by_user.slice(0, 10) as r}
              <tr><td>{r.name}</td><td>{fmtInt(r.calls)}</td><td>{fmtInt(r.tokens)}</td><td>${fmt(r.cost, 4)}</td></tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}

  {#if heatmapGrid.length}
    <h3 class="sub-h">Upload heatmap (14d × 24h)</h3>
    <div class="heatmap">
      <div class="hm-hours">
        <span></span>
        {#each Array(24) as _, h}<span class="hm-hour">{h}</span>{/each}
      </div>
      {#each heatmapGrid as row}
        <div class="hm-row">
          <span class="hm-day">{row.day.slice(5)}</span>
          {#each row.hours as cell}
            <span class="hm-cell" style="background: rgba(201,100,66,{cell.intensity * 0.9 + (cell.n ? 0.08 : 0)})" title="{row.day} {cell.h}:00 — {cell.n} uploads"></span>
          {/each}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 16px; }
  .head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  .muted { color: var(--text-muted); }
  .sub-h { font-size: 12px; text-transform: uppercase; color: var(--text-muted); margin: 20px 0 8px; letter-spacing: 0.05em; font-weight: 600; }

  .funnel { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .step { flex: 1; min-width: 110px; padding: 10px; border: 1px solid var(--border); border-radius: var(--r-sm); text-align: center; }
  .step-n { font-size: 22px; font-weight: 700; color: var(--accent, #c96442); }
  .step-l { font-size: 11px; color: var(--text-muted); text-transform: uppercase; margin-top: 2px; }
  .arrow { color: var(--text-muted); font-weight: 700; }

  .cost-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 12px; }
  .kpi { padding: 10px; background: var(--surface-2, var(--surface)); border-radius: var(--r-sm); border: 1px solid var(--border); }
  .kpi-n { font-size: 18px; font-weight: 700; }
  .kpi-l { font-size: 11px; color: var(--text-muted); }

  .cost-tables { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .cost-col h4 { margin: 0 0 6px; font-size: 12px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th, td { padding: 4px 8px; text-align: left; border-bottom: 1px solid var(--border); }
  th { color: var(--text-muted); font-weight: 600; }

  .heatmap { display: flex; flex-direction: column; gap: 2px; overflow-x: auto; }
  .hm-hours { display: grid; grid-template-columns: 40px repeat(24, 1fr); gap: 2px; font-size: 9px; color: var(--text-muted); }
  .hm-row { display: grid; grid-template-columns: 40px repeat(24, 1fr); gap: 2px; align-items: center; }
  .hm-day { font-size: 10px; color: var(--text-muted); font-family: var(--font-mono); }
  .hm-cell { aspect-ratio: 1; min-width: 14px; border-radius: 2px; background: var(--surface-2, rgba(0,0,0,0.04)); }
  .hm-hour { text-align: center; }

  .small { font-size: 11px; margin-top: 0; }
  .jobs { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
  .job-row {
    display: grid; grid-template-columns: 140px 1fr auto auto; gap: 10px; align-items: center;
    padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--r-sm);
    background: var(--surface-2, var(--surface));
  }
  .job-id { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); }
  .job-label { font-size: 13px; }
  .run-btn {
    padding: 6px 12px; background: var(--accent, #c96442); color: white;
    border: none; border-radius: var(--r-sm); cursor: pointer; font-family: inherit;
    font-size: 12px; font-weight: 600;
  }
  .run-btn:disabled { opacity: 0.6; cursor: not-allowed; }
  .job-result { font-size: 11px; color: #50b464; font-weight: 600; }
  .sched { display: flex; flex-direction: column; gap: 6px; margin-bottom: 16px; }
  .sched-row {
    display: grid;
    grid-template-columns: 140px 1fr auto auto auto;
    gap: 10px; align-items: center;
    padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--r-sm);
    background: var(--surface-2, var(--surface));
  }
  .sched-id { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); }
  .sched-cur { font-size: 12px; color: var(--text-muted); }
  .sched-cur b { color: var(--text); font-family: var(--font-mono); }
  .sched-mode { font-size: 12px; display: flex; align-items: center; gap: 4px; }
  .sched-mode .num {
    width: 50px; padding: 4px 6px; border: 1px solid var(--border);
    border-radius: var(--r-sm); background: var(--surface); color: var(--text);
    font-family: var(--font-mono); font-size: 12px; text-align: center;
  }
  .sw { display: flex; align-items: center; gap: 4px; font-size: 11px; cursor: pointer; }

  .job-toast {
    padding: 8px 12px; background: var(--surface-2, var(--surface)); border: 1px solid var(--border);
    border-radius: var(--r-sm); font-size: 13px; margin-bottom: 12px;
  }
</style>
