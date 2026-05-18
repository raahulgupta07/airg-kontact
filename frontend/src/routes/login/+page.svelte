<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { auth } from '$lib/auth.svelte';

  let identifier = $state('');
  let secret = $state('');
  let error = $state('');
  let busy = $state(false);
  let showPassword = $state(false);
  let remember = $state(false);

  const REMEMBER_KEY = 'kontact-remember';

  onMount(async () => {
    // Restore remembered credentials
    try {
      const raw = localStorage.getItem(REMEMBER_KEY);
      if (raw) {
        const saved = JSON.parse(atob(raw));
        identifier = saved.identifier || '';
        secret = saved.secret || '';
        remember = true;
      }
    } catch {}

    if (!auth.user) {
      await auth.refresh();
    }
    if (auth.user) {
      goto('/');
    }
  });

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    if (busy) return;
    busy = true;
    error = '';
    try {
      await auth.login(identifier.trim(), secret);
      if (remember) {
        try {
          localStorage.setItem(
            REMEMBER_KEY,
            btoa(JSON.stringify({ identifier: identifier.trim(), secret }))
          );
        } catch {}
      } else {
        try { localStorage.removeItem(REMEMBER_KEY); } catch {}
      }
      goto('/');
    } catch (err) {
      error = err instanceof Error ? err.message : 'Login failed';
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head><title>Sign in | Kontact</title></svelte:head>

<div class="login-wrap">
  <div class="login-card">
    <h1 class="brand">Kontact</h1>
    <p class="subtitle">Sign in to continue</p>

    {#if error}
      <div class="err" role="alert">{error}</div>
    {/if}

    <form onsubmit={submit} novalidate>
      <label class="field">
        <span>Email</span>
        <input
          class="input"
          type="email"
          bind:value={identifier}
          autocomplete="email"
          required
          placeholder="you@example.com"
        />
      </label>

      <label class="field">
        <span>Password</span>
        <div class="input-wrap">
          <input
            class="input pw"
            type={showPassword ? 'text' : 'password'}
            bind:value={secret}
            autocomplete="current-password"
            inputmode="text"
            required
            placeholder="••••••••"
          />
          <button
            type="button"
            class="reveal-btn"
            onclick={() => (showPassword = !showPassword)}
            aria-label={showPassword ? 'Hide password' : 'Show password'}
            tabindex="-1"
          >
            {#if showPassword}
              <!-- eye-off -->
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M9.88 9.88a3 3 0 0 0 4.24 4.24"/>
                <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/>
                <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/>
                <line x1="2" y1="2" x2="22" y2="22"/>
              </svg>
            {:else}
              <!-- eye -->
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
            {/if}
          </button>
        </div>
      </label>

      <label class="remember">
        <input type="checkbox" bind:checked={remember} />
        <span>Remember me on this device</span>
      </label>

      <button
        class="send-btn full"
        type="submit"
        disabled={busy || !identifier || !secret}
      >
        {busy ? 'Signing in…' : 'Sign in'}
      </button>
    </form>

    {#if remember}
      <p class="warn-hint">⚠ Credentials stored locally. Use only on your own device.</p>
    {/if}
  </div>
</div>

<style>
  .login-wrap {
    min-height: 100vh;
    min-height: 100dvh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: var(--bg);
  }
  .login-card {
    width: 100%;
    max-width: 380px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    padding: 36px 28px;
    box-shadow: var(--shadow-sm);
  }
  .brand {
    font-family: var(--font-serif, Georgia, serif);
    font-size: 32px;
    font-weight: 600;
    color: var(--accent);
    margin: 0;
    text-align: center;
    letter-spacing: -0.01em;
  }
  .subtitle {
    text-align: center;
    color: var(--text-muted);
    margin: 4px 0 28px;
    font-size: 14px;
  }
  .field {
    display: block;
    margin-bottom: 14px;
  }
  .field span {
    display: block;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-muted);
    margin-bottom: 6px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .input {
    width: 100%;
  }
  .input-wrap {
    position: relative;
  }
  .input.pw {
    padding-right: 42px;
  }
  .reveal-btn {
    position: absolute;
    top: 50%;
    right: 8px;
    transform: translateY(-50%);
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: none;
    border: none;
    color: var(--text-muted);
    border-radius: var(--r-sm);
    cursor: pointer;
    transition: color 0.12s, background 0.12s;
  }
  .reveal-btn:hover {
    color: var(--accent);
    background: var(--accent-soft);
  }
  .remember {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 4px 0 14px;
    font-size: 13px;
    color: var(--text-muted);
    cursor: pointer;
    user-select: none;
  }
  .remember input {
    width: 16px;
    height: 16px;
    accent-color: var(--accent);
    cursor: pointer;
  }
  .send-btn.full {
    width: 100%;
    margin-top: 4px;
    min-height: 44px;
    font-weight: 600;
  }
  .err {
    background: rgba(181, 69, 61, 0.08);
    border: 1px solid var(--danger);
    color: var(--danger);
    padding: 10px 12px;
    border-radius: var(--r-md);
    font-size: 13px;
    margin-bottom: 14px;
  }
  .hint {
    font-size: 12px;
    color: var(--text-faint);
    text-align: center;
    margin: 18px 0 0;
  }
  .warn-hint {
    font-size: 11px;
    color: var(--warning);
    text-align: center;
    margin: 6px 0 0;
  }
</style>
