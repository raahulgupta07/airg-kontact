<script lang="ts">
  import { undoToasts } from '$lib/undoToast.svelte';
</script>

<div class="undo-stack" aria-live="polite">
  {#each undoToasts.toasts as t (t.id)}
    <div class="undo-toast" role="status">
      <span class="undo-msg">{t.message}</span>
      <button class="undo-btn" onclick={() => undoToasts.undo(t.id)}>Undo</button>
      <button class="undo-x" onclick={() => undoToasts.dismiss(t.id)} aria-label="Dismiss">×</button>
    </div>
  {/each}
</div>

<style>
  .undo-stack {
    position: fixed;
    bottom: 80px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    flex-direction: column;
    gap: 8px;
    z-index: 150;
    max-width: 90vw;
  }
  .undo-toast {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-md, 8px);
    box-shadow: 0 6px 20px rgba(0,0,0,0.18);
    font-size: 13px;
    animation: undo-in 0.18s ease-out;
  }
  @keyframes undo-in {
    from { transform: translateY(8px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }
  .undo-msg { flex: 1; color: var(--text); }
  .undo-btn {
    background: var(--accent, #c96442);
    color: white;
    border: none;
    padding: 4px 10px;
    border-radius: var(--r-sm);
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    font-size: 12px;
  }
  .undo-x {
    background: transparent;
    border: none;
    color: var(--text-muted);
    font-size: 16px;
    cursor: pointer;
    padding: 0 4px;
  }
</style>
