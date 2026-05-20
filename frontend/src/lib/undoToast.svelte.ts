// Tiny global undo-toast store. Components push toasts after destructive ops
// (delete, merge, reject) with a 5s window to undo.

export interface UndoToast {
  id: string;
  message: string;
  onUndo: () => void | Promise<void>;
  expiresAt: number;
}

class UndoToastState {
  toasts: UndoToast[] = $state([]);

  push(message: string, onUndo: () => void | Promise<void>, ttlMs = 5000) {
    const id = 'ut-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 6);
    const t: UndoToast = { id, message, onUndo, expiresAt: Date.now() + ttlMs };
    this.toasts = [...this.toasts, t];
    setTimeout(() => this.dismiss(id), ttlMs);
  }

  dismiss(id: string) {
    this.toasts = this.toasts.filter(t => t.id !== id);
  }

  async undo(id: string) {
    const t = this.toasts.find(x => x.id === id);
    if (!t) return;
    try { await t.onUndo(); } catch (e) { console.error('undo failed', e); }
    this.dismiss(id);
  }
}

export const undoToasts = new UndoToastState();
