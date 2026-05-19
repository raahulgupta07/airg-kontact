<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { auth } from '$lib/auth.svelte';

  let me = $state<any>(null);
  let loading = $state(true);

  let currentPw = $state('');
  let newPw = $state('');
  let confirmPw = $state('');
  let showCurrent = $state(false);
  let showNew = $state(false);
  let showConfirm = $state(false);

  let busy = $state(false);
  let msg = $state<{ kind: 'ok' | 'err'; text: string } | null>(null);

  onMount(async () => {
    try {
      const r = await fetch('/api/auth/me', { credentials: 'include' });
      if (r.ok) {
        me = await r.json();
      } else if (r.status === 401) {
        goto('/login');
      }
    } finally {
      loading = false;
    }
  });

  function initials(name: string) {
    if (!name) return '?';
    return name.trim().split(/\s+/).slice(0, 2).map(p => p[0]?.toUpperCase() || '').join('') || '?';
  }

  function fmtDate(s: string | null) {
    if (!s) return '—';
    try {
      const d = new Date(s);
      return d.toLocaleString();
    } catch {
      return s;
    }
  }

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    if (busy) return;
    msg = null;
    if (newPw.length < 8) {
      msg = { kind: 'err', text: 'New password must be at least 8 characters.' };
      return;
    }
    if (newPw !== confirmPw) {
      msg = { kind: 'err', text: 'New password and confirmation do not match.' };
      return;
    }
    if (newPw === currentPw) {
      msg = { kind: 'err', text: 'New password must differ from current.' };
      return;
    }
    busy = true;
    try {
      const r = await fetch('/api/auth/change-password', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: currentPw, new_password: newPw }),
      });
      if (r.ok) {
        msg = { kind: 'ok', text: 'Password updated. Use it next time you sign in.' };
        currentPw = ''; newPw = ''; confirmPw = '';
      } else {
        const e = await r.json().catch(() => ({}));
        msg = { kind: 'err', text: e.detail || `Failed (${r.status})` };
      }
    } catch (err) {
      msg = { kind: 'err', text: 'Network error' };
    } finally {
      busy = false;
    }
  }

  async function signOut() {
    await auth.logout();
    goto('/login');
  }
</script>

<svelte:head><title>Profile | Kontact</title></svelte:head>

<div class="profile-page">
  <header class="page-head">
    <h1 class="page-title">Profile</h1>
  </header>

  {#if loading}
    <div class="muted">Loading…</div>
  {:else if me}
    <section class="card identity">
      <div class="avatar">{initials(me.name)}</div>
      <div class="identity-meta">
        <div class="identity-name">{me.name}</div>
        <div class="identity-email">{me.email}</div>
        <div class="identity-sub">
          <span class="chip">{me.role}</span>
          {#if me.created_at}· since {fmtDate(me.created_at).split(',')[0]}{/if}
        </div>
      </div>
    </section>

    <section class="card">
      <h2 class="section-h">Change password</h2>

      {#if msg}
        <div class="banner {msg.kind === 'ok' ? 'banner-ok' : 'banner-err'}" role="alert">
          {msg.text}
        </div>
      {/if}

      <form onsubmit={submit} novalidate>
        <label class="field">
          <span>Current password</span>
          <div class="input-wrap">
            <input
              class="input"
              type={showCurrent ? 'text' : 'password'}
              bind:value={currentPw}
              autocomplete="current-password"
              required
            />
            <button type="button" class="reveal" tabindex="-1"
              onclick={() => (showCurrent = !showCurrent)}
              aria-label={showCurrent ? 'Hide' : 'Show'}>
              {showCurrent ? '🙈' : '👁'}
            </button>
          </div>
        </label>

        <label class="field">
          <span>New password</span>
          <div class="input-wrap">
            <input
              class="input"
              type={showNew ? 'text' : 'password'}
              bind:value={newPw}
              autocomplete="new-password"
              minlength="8"
              required
            />
            <button type="button" class="reveal" tabindex="-1"
              onclick={() => (showNew = !showNew)}
              aria-label={showNew ? 'Hide' : 'Show'}>
              {showNew ? '🙈' : '👁'}
            </button>
          </div>
          <p class="hint-line">Min 8 characters.</p>
        </label>

        <label class="field">
          <span>Confirm new password</span>
          <div class="input-wrap">
            <input
              class="input"
              type={showConfirm ? 'text' : 'password'}
              bind:value={confirmPw}
              autocomplete="new-password"
              required
            />
            <button type="button" class="reveal" tabindex="-1"
              onclick={() => (showConfirm = !showConfirm)}
              aria-label={showConfirm ? 'Hide' : 'Show'}>
              {showConfirm ? '🙈' : '👁'}
            </button>
          </div>
        </label>

        <button
          type="submit"
          class="send-btn full"
          disabled={busy || !currentPw || !newPw || !confirmPw}
        >
          {busy ? 'Updating…' : 'Update password'}
        </button>
      </form>
    </section>

    <section class="card">
      <h2 class="section-h">Account</h2>
      <div class="kv">
        <span>UUID</span><code class="mono">{me.uuid}</code>
        <span>Role</span><span>{me.role}</span>
        <span>Created</span><span>{fmtDate(me.created_at)}</span>
        <span>Last login</span><span>{fmtDate(me.last_login)}</span>
        {#if me.phone_e164}<span>Phone</span><span>{me.phone_e164}</span>{/if}
      </div>
      <button class="btn-ghost full" onclick={signOut}>Sign out</button>
    </section>
  {/if}
</div>

<style>
  .profile-page {
    max-width: 560px;
    margin: 0 auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .page-head { margin-bottom: 4px; }
  .page-title { font-family: var(--font-serif, Georgia, serif); font-size: 28px; margin: 0; color: var(--text); }
  .muted { color: var(--text-muted); text-align: center; padding: 32px; }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    padding: 20px;
  }
  .identity { display: flex; align-items: center; gap: 16px; }
  .avatar {
    width: 56px; height: 56px;
    border-radius: 50%;
    background: var(--accent);
    color: white;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px; font-weight: 600;
    flex-shrink: 0;
  }
  .identity-meta { flex: 1; min-width: 0; }
  .identity-name { font-size: 18px; font-weight: 600; color: var(--text); }
  .identity-email { color: var(--text-muted); font-size: 14px; margin-top: 2px; }
  .identity-sub { color: var(--text-faint); font-size: 12px; margin-top: 4px; }
  .chip {
    display: inline-block;
    padding: 2px 8px;
    background: var(--accent-soft, rgba(201,100,66,0.12));
    color: var(--accent);
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    margin-right: 4px;
  }

  .section-h {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    font-weight: 600;
    margin: 0 0 14px;
  }

  .field { display: block; margin-bottom: 12px; }
  .field > span {
    display: block;
    font-size: 11px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 600;
    margin-bottom: 6px;
  }
  .input-wrap { position: relative; }
  .input {
    width: 100%;
    padding: 9px 38px 9px 12px;
    border: 1px solid var(--border);
    border-radius: var(--r-md);
    background: var(--surface);
    color: var(--text);
    font-size: 14px;
    font-family: inherit;
  }
  .input:focus { outline: none; border-color: var(--accent); }
  .reveal {
    position: absolute;
    right: 6px;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    width: 30px;
    height: 30px;
    cursor: pointer;
    font-size: 14px;
    color: var(--text-muted);
  }
  .hint-line { font-size: 11px; color: var(--text-faint); margin: 4px 0 0; }

  .send-btn.full {
    width: 100%;
    margin-top: 4px;
    min-height: 42px;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: var(--r-md);
    font-weight: 600;
    font-size: 14px;
    cursor: pointer;
  }
  .send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-ghost.full {
    width: 100%;
    margin-top: 12px;
    padding: 10px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text);
    border-radius: var(--r-md);
    cursor: pointer;
    font-family: inherit;
    font-size: 14px;
  }
  .btn-ghost:hover { background: var(--surface-2, rgba(0,0,0,0.02)); }

  .banner { padding: 10px 12px; border-radius: var(--r-md); font-size: 13px; margin-bottom: 12px; }
  .banner-ok { background: rgba(34,197,94,0.08); border: 1px solid #22c55e; color: #15803d; }
  .banner-err { background: rgba(181,69,61,0.08); border: 1px solid var(--danger); color: var(--danger); }

  .kv {
    display: grid;
    grid-template-columns: 110px 1fr;
    gap: 6px 12px;
    font-size: 13px;
  }
  .kv > span:nth-child(odd) { color: var(--text-muted); font-size: 12px; }
  .mono { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 11px; word-break: break-all; }
</style>
