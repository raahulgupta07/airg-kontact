<script lang="ts">
  let { icon = '📭', title = 'Nothing here yet', hint = '', cta = '', oncta } = $props<{
    icon?: string; title?: string; hint?: string; cta?: string; oncta?: () => void;
  }>();
</script>

<div class="empty">
  <div class="empty-icon">{icon}</div>
  <h3 class="empty-title">{title}</h3>
  {#if hint}<p class="empty-hint">{hint}</p>{/if}
  {#if cta}<button class="empty-cta" onclick={() => oncta?.()}>{cta}</button>{/if}
</div>

<style>
  .empty {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: 48px 16px; text-align: center; color: var(--text-muted);
  }
  .empty-icon { font-size: 48px; opacity: 0.6; margin-bottom: 12px; }
  .empty-title { font-size: 16px; font-weight: 600; color: var(--text); margin: 0 0 6px; }
  .empty-hint { font-size: 13px; max-width: 360px; line-height: 1.5; margin: 0 0 16px; }
  .empty-cta {
    padding: 8px 18px; background: var(--accent, #c96442); color: white;
    border: none; border-radius: var(--r-sm); cursor: pointer; font-family: inherit;
    font-weight: 600; font-size: 13px;
  }
  .empty-cta:hover { filter: brightness(1.05); }
</style>
