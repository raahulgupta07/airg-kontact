<script lang="ts">
  import { onMount } from 'svelte';
  import { auth, type User, type UserRole } from '$lib/auth.svelte';

  type UserRow = User & {
    created_at?: string;
    last_login_at?: string | null;
  };

  let users = $state<UserRow[]>([]);
  let loading = $state(true);
  let listErr = $state('');

  let showModal = $state(false);
  let editing = $state<UserRow | null>(null);
  let saving = $state(false);
  let err = $state('');

  // Reset password modal
  let resetTarget = $state<UserRow | null>(null);
  let resetPw = $state('');
  let resetBusy = $state(false);
  let resetMsg = $state('');

  function openReset(u: UserRow) {
    resetTarget = u;
    resetPw = '';
    resetMsg = '';
  }
  function closeReset() { resetTarget = null; }
  function genPw() {
    // 14-char random URL-safe
    const chars = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$';
    let s = '';
    for (let i = 0; i < 14; i++) s += chars[Math.floor(Math.random() * chars.length)];
    resetPw = s;
  }
  async function submitReset() {
    if (!resetTarget || resetPw.length < 8) {
      resetMsg = 'Password must be at least 8 characters.';
      return;
    }
    resetBusy = true;
    resetMsg = '';
    try {
      const r = await fetch(`/api/users/${resetTarget.uuid}`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: resetPw }),
      });
      if (r.ok) {
        resetMsg = `OK — give this password to ${resetTarget.name}: ${resetPw}`;
        // Don't auto-close — admin needs to copy
      } else {
        const e = await r.json().catch(() => ({}));
        resetMsg = e.detail || `Failed (${r.status})`;
      }
    } catch {
      resetMsg = 'Network error';
    } finally {
      resetBusy = false;
    }
  }

  type FormShape = {
    name: string;
    email: string;
    phone: string;
    password: string;
    pin: string;
    role: UserRole;
  };

  const emptyForm = (): FormShape => ({
    name: '',
    email: '',
    phone: '',
    password: '',
    pin: '',
    role: 'user'
  });

  let form = $state<FormShape>(emptyForm());

  async function load() {
    loading = true;
    listErr = '';
    try {
      const r = await fetch('/api/users', { credentials: 'include' });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        listErr = e.detail || `Failed to load (${r.status})`;
        users = [];
      } else {
        users = await r.json();
      }
    } catch (e) {
      listErr = e instanceof Error ? e.message : 'Network error';
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    if (auth.isAdmin) load();
  });

  function openNew() {
    editing = null;
    form = emptyForm();
    err = '';
    showModal = true;
  }

  function openEdit(u: UserRow) {
    if (u.role === 'super_admin' && !auth.isSuperAdmin) return;
    editing = u;
    form = {
      name: u.name,
      email: u.email || '',
      phone: u.phone_e164 || '',
      password: '',
      pin: '',
      role: u.role
    };
    err = '';
    showModal = true;
  }

  function closeModal() {
    if (saving) return;
    showModal = false;
    editing = null;
    form = emptyForm();
    err = '';
  }

  async function save(e: SubmitEvent) {
    e.preventDefault();
    if (saving) return;

    // Light client-side validation
    if (form.pin && !/^\d{4}$/.test(form.pin)) {
      err = 'PIN must be exactly 4 digits';
      return;
    }
    if (!editing && !form.password && !form.pin) {
      err = 'Set a password or PIN';
      return;
    }

    saving = true;
    err = '';

    // For PATCH, only include fields that changed / are non-empty
    const payload: Record<string, unknown> = {
      name: form.name,
      email: form.email || null,
      phone: form.phone || null,
      role: form.role
    };
    if (form.password) payload.password = form.password;
    if (form.pin) payload.pin = form.pin;

    const url = editing ? `/api/users/${editing.uuid}` : '/api/users';
    const method = editing ? 'PATCH' : 'POST';

    try {
      const r = await fetch(url, {
        method,
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!r.ok) {
        const e2 = await r.json().catch(() => ({}));
        err = e2.detail || `Save failed (${r.status})`;
        return;
      }
      showModal = false;
      editing = null;
      form = emptyForm();
      await load();
    } catch (e2) {
      err = e2 instanceof Error ? e2.message : 'Network error';
    } finally {
      saving = false;
    }
  }

  async function del(u: UserRow) {
    if (u.role === 'super_admin') return;
    if (u.uuid === auth.user?.uuid) {
      alert('You cannot delete your own account.');
      return;
    }
    if (!confirm(`Delete ${u.name}? This cannot be undone.`)) return;
    try {
      const r = await fetch(`/api/users/${u.uuid}`, {
        method: 'DELETE',
        credentials: 'include'
      });
      if (r.ok) {
        await load();
      } else {
        const e = await r.json().catch(() => ({}));
        alert(e.detail || `Delete failed (${r.status})`);
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Network error');
    }
  }

  function roleLabel(r: UserRole): string {
    if (r === 'super_admin') return 'Super admin';
    if (r === 'admin') return 'Admin';
    return 'User';
  }

  function fmtDate(s?: string | null): string {
    if (!s) return '—';
    try {
      const d = new Date(s);
      if (Number.isNaN(d.getTime())) return s;
      return d.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return s;
    }
  }
</script>

<svelte:head><title>Users | Kontact</title></svelte:head>

{#if !auth.isAdmin}
  <div class="forbidden">
    <div class="card">
      <h2>Forbidden</h2>
      <p>You don't have permission to view this page.</p>
    </div>
  </div>
{:else}
  <header class="page-head">
    <div class="head-left">
      <h1 class="page-title">Users</h1>
      <span class="head-count">
        {users.length} {users.length === 1 ? 'user' : 'users'}
      </span>
    </div>
    <div class="head-right">
      <button class="send-btn" onclick={openNew}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <line x1="12" y1="5" x2="12" y2="19"/>
          <line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        New user
      </button>
    </div>
  </header>

  {#if listErr}
    <div class="err-banner">{listErr}</div>
  {/if}

  <div class="card table-card">
    {#if loading}
      <p class="muted">Loading users…</p>
    {:else if users.length === 0}
      <p class="muted">No users yet.</p>
    {:else}
      <div class="table-wrap">
        <table class="users-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Phone</th>
              <th>Role</th>
              <th>Last login</th>
              <th class="actions-col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {#each users as u (u.uuid)}
              {@const locked = u.role === 'super_admin' && !auth.isSuperAdmin}
              {@const isSelf = u.uuid === auth.user?.uuid}
              <tr>
                <td class="name-cell">
                  <span>{u.name}</span>
                  {#if isSelf}<span class="chip chip-accent self-chip">You</span>{/if}
                </td>
                <td class="muted-cell">{u.email || '—'}</td>
                <td class="muted-cell">{u.phone_e164 || '—'}</td>
                <td>
                  <span class="chip" class:chip-accent={u.role !== 'user'}>
                    {roleLabel(u.role)}
                  </span>
                </td>
                <td class="muted-cell">{fmtDate(u.last_login_at)}</td>
                <td class="actions-col">
                  {#if locked}
                    <span class="lock" title="Super admin — protected">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <rect x="3" y="11" width="18" height="11" rx="2"/>
                        <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                      </svg>
                    </span>
                  {:else}
                    <div class="row-actions">
                      <button class="btn-ghost xs" onclick={() => openEdit(u)}>Edit</button>
                      <button class="btn-ghost xs" onclick={() => openReset(u)} title="Reset password">Reset PW</button>
                      {#if !isSelf && u.role !== 'super_admin'}
                        <button class="btn-ghost xs danger" onclick={() => del(u)}>Delete</button>
                      {/if}
                    </div>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </div>
{/if}

{#if showModal}
  <button
    type="button"
    class="modal-backdrop"
    aria-label="Close"
    onclick={closeModal}
  ></button>
  <div class="modal-wrap" role="dialog" aria-modal="true" aria-labelledby="modal-title">
    <div class="modal">
      <header class="modal-head">
        <h2 id="modal-title">{editing ? 'Edit user' : 'New user'}</h2>
        <button class="btn-ghost xs" onclick={closeModal} aria-label="Close" disabled={saving}>✕</button>
      </header>

      {#if err}
        <div class="err-banner">{err}</div>
      {/if}

      <form onsubmit={save}>
        <label class="mfield">
          <span>Name</span>
          <input class="input" type="text" bind:value={form.name} required autocomplete="name" />
        </label>

        <div class="mrow">
          <label class="mfield">
            <span>Email</span>
            <input class="input" type="email" bind:value={form.email} autocomplete="email" placeholder="optional" />
          </label>
          <label class="mfield">
            <span>Phone</span>
            <input class="input" type="tel" bind:value={form.phone} autocomplete="tel" placeholder="+95…" />
          </label>
        </div>

        <div class="mrow">
          <label class="mfield">
            <span>{editing ? 'New password' : 'Password'}</span>
            <input
              class="input"
              type="password"
              bind:value={form.password}
              autocomplete="new-password"
              placeholder={editing ? 'leave blank to keep' : 'min 8 chars'}
            />
          </label>
          <label class="mfield">
            <span>{editing ? 'New PIN' : 'PIN'}</span>
            <input
              class="input"
              type="text"
              inputmode="numeric"
              pattern="[0-9]{'{'}4{'}'}"
              maxlength="4"
              bind:value={form.pin}
              placeholder={editing ? 'leave blank' : '4 digits'}
            />
          </label>
        </div>

        <label class="mfield">
          <span>Role</span>
          {#if editing?.role === 'super_admin'}
            <input class="input" type="text" value="Super admin" disabled />
          {:else}
            <select class="input" bind:value={form.role}>
              <option value="user">User</option>
              <option value="admin">Admin</option>
              {#if auth.isSuperAdmin}
                <option value="super_admin">Super admin</option>
              {/if}
            </select>
          {/if}
        </label>

        <footer class="modal-foot">
          <button type="button" class="btn-ghost" onclick={closeModal} disabled={saving}>Cancel</button>
          <button type="submit" class="send-btn" disabled={saving || !form.name}>
            {saving ? 'Saving…' : editing ? 'Save changes' : 'Create user'}
          </button>
        </footer>
      </form>
    </div>
  </div>
{/if}

{#if resetTarget}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="modal-backdrop" onclick={closeReset}>
    <div class="modal-card" onclick={(e) => e.stopPropagation()}>
      <h3 class="modal-title">Reset password</h3>
      <p class="modal-sub">for <b>{resetTarget.name}</b> ({resetTarget.email})</p>

      <label class="field">
        <span>New password</span>
        <input
          type="text"
          bind:value={resetPw}
          minlength="8"
          placeholder="At least 8 characters"
          class="input"
        />
      </label>

      <div class="reset-actions">
        <button class="btn-ghost" type="button" onclick={genPw}>Generate</button>
        <div class="spacer"></div>
        <button class="btn-ghost" type="button" onclick={closeReset}>Cancel</button>
        <button class="send-btn" type="button" disabled={resetBusy || resetPw.length < 8} onclick={submitReset}>
          {resetBusy ? 'Saving…' : 'Reset'}
        </button>
      </div>

      {#if resetMsg}
        <div class="banner-info">{resetMsg}</div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .forbidden {
    max-width: 480px;
    margin: 64px auto;
  }

  .page-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 12px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }
  .page-title { margin: 0; font-size: 24px; font-weight: 600; color: var(--text); }
  .head-count { font-size: 13px; color: var(--text-muted); margin-left: 12px; }
  .head-right { display: flex; gap: 8px; }
  .head-right .send-btn {
    display: inline-flex; align-items: center; gap: 6px;
  }

  .err-banner {
    background: rgba(181, 69, 61, 0.08);
    border: 1px solid var(--danger);
    color: var(--danger);
    padding: 10px 12px;
    border-radius: var(--r-md);
    font-size: 13px;
    margin-bottom: 14px;
  }

  .table-card { padding: 0; overflow: hidden; }
  .table-wrap { overflow-x: auto; }

  .users-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }
  .users-table th,
  .users-table td {
    text-align: left;
    padding: 12px 14px;
    border-bottom: 1px solid var(--border);
    vertical-align: middle;
  }
  .users-table th {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    background: var(--surface-2);
  }
  .users-table tbody tr:last-child td { border-bottom: none; }
  .users-table tbody tr:hover { background: var(--surface-2); }

  .muted, .muted-cell { color: var(--text-muted); }
  .name-cell { font-weight: 500; color: var(--text); display: flex; align-items: center; gap: 8px; }
  .self-chip { font-size: 10px; padding: 2px 6px; }

  .actions-col { text-align: right; width: 1%; white-space: nowrap; }
  .row-actions { display: inline-flex; gap: 6px; justify-content: flex-end; }

  .btn-ghost.xs {
    padding: 5px 10px;
    font-size: 12px;
    min-height: 28px;
    border-radius: var(--r-sm);
  }
  .btn-ghost.xs.danger {
    color: var(--danger);
    border-color: var(--border);
  }
  .btn-ghost.xs.danger:hover {
    background: rgba(181, 69, 61, 0.08);
    border-color: var(--danger);
  }

  .lock {
    display: inline-flex;
    color: var(--text-faint);
    padding: 4px;
  }

  /* Modal */
  .modal-wrap {
    position: fixed; inset: 0;
    display: flex; align-items: center; justify-content: center;
    padding: 16px;
    z-index: 210;
    pointer-events: none;
  }
  .modal-wrap .modal {
    pointer-events: auto;
    width: 100%;
    max-width: 520px;
    padding: 20px 22px;
  }
  .modal-head {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 14px;
  }
  .modal-head h2 { margin: 0; font-size: 18px; }
  .mfield { display: block; margin-bottom: 12px; }
  .mfield span {
    display: block;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-muted);
    margin-bottom: 6px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .mrow {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  .modal-foot {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 18px;
    padding-top: 14px;
    border-top: 1px solid var(--border);
  }

  @media (max-width: 520px) {
    .mrow { grid-template-columns: 1fr; }
  }

  /* Reset-password modal */
  .modal-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    padding: 22px;
    width: 100%;
    max-width: 420px;
  }
  .modal-title { margin: 0; font-size: 17px; }
  .modal-sub { color: var(--text-muted); font-size: 13px; margin: 4px 0 14px; }
  .reset-actions {
    display: flex; gap: 8px; align-items: center; margin-top: 4px;
  }
  .reset-actions .spacer { flex: 1; }
  .reset-actions .btn-ghost, .reset-actions .send-btn {
    padding: 8px 14px;
  }
  .banner-info {
    margin-top: 14px;
    padding: 10px 12px;
    background: var(--accent-soft, rgba(201,100,66,0.1));
    border: 1px solid var(--accent);
    color: var(--text);
    border-radius: var(--r-md);
    font-size: 12px;
    word-break: break-all;
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
  }
</style>
