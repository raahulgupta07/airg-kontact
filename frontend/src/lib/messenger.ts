// Messenger deeplink helpers + inline SVG icons.

export type MessengerKind =
  | 'whatsapp' | 'viber' | 'telegram' | 'line' | 'wechat' | 'signal' | 'zalo'
  | 'phone' | 'email';

export interface MessengerLink {
  kind: MessengerKind;
  label: string;
  url: string;
  color: string;
}

const stripPlus = (s: string) => (s || '').replace(/[^\d]/g, '');
const safe = (s: unknown) => (typeof s === 'string' ? s.trim() : '');

/**
 * Build a deeplink list from a contact object. Mirrors the backend
 * `openMessengerDeeplink` resolver so links work even without the server.
 */
export function buildMessengerLinks(contact: Record<string, unknown> = {}): MessengerLink[] {
  const out: MessengerLink[] = [];
  const phone = safe(contact.phone) || safe(contact.telephone);
  const phoneDigits = stripPlus(phone);
  const email = safe(contact.email);

  const whatsapp = safe(contact.whatsapp) || phoneDigits;
  const viber = safe(contact.viber) || phoneDigits;
  const telegram = safe(contact.telegram) || safe(contact.telegram_id) || safe(contact.telegram_handle);
  const lineId = safe(contact.line_id) || safe(contact.line);
  const wechatId = safe(contact.wechat_id) || safe(contact.wechat);
  const wechatQr = safe(contact.wechat_qr_url) || safe(contact.wechat_qr);
  const signal = safe(contact.signal) || phoneDigits;
  const zalo = safe(contact.zalo) || phoneDigits;

  if (phone) out.push({ kind: 'phone', label: 'Call', url: `tel:${phone}`, color: '#383832' });
  if (email) out.push({ kind: 'email', label: 'Email', url: `mailto:${email}`, color: '#475569' });
  if (whatsapp) out.push({ kind: 'whatsapp', label: 'WhatsApp', url: `https://wa.me/${stripPlus(whatsapp)}`, color: '#25D366' });
  if (viber) out.push({ kind: 'viber', label: 'Viber', url: `viber://add?number=${stripPlus(viber)}`, color: '#7360F2' });
  if (telegram) {
    const handle = telegram.replace(/^@/, '');
    out.push({ kind: 'telegram', label: 'Telegram', url: `https://t.me/${handle}`, color: '#26A5E4' });
  }
  if (lineId) out.push({ kind: 'line', label: 'LINE', url: `https://line.me/ti/p/~${lineId.replace(/^~/, '')}`, color: '#06C755' });
  if (wechatId || wechatQr) {
    out.push({
      kind: 'wechat',
      label: 'WeChat',
      url: wechatQr || `weixin://dl/chat?${wechatId}`,
      color: '#07C160'
    });
  }
  if (signal) out.push({ kind: 'signal', label: 'Signal', url: `https://signal.me/#p/+${stripPlus(signal)}`, color: '#3A76F0' });
  if (zalo) out.push({ kind: 'zalo', label: 'Zalo', url: `https://zalo.me/${stripPlus(zalo)}`, color: '#0068FF' });

  return out;
}

/** Inline SVG (as string) for a messenger kind. Stroke uses currentColor. */
export function messengerIcon(kind: MessengerKind): string {
  switch (kind) {
    case 'phone':
      return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.37 1.9.72 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.35 1.85.59 2.81.72A2 2 0 0 1 22 16.92z"/></svg>`;
    case 'email':
      return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>`;
    case 'whatsapp':
      return `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M17.5 14.4c-.3-.2-1.8-.9-2.1-1-.3-.1-.5-.2-.7.2s-.8 1-.9 1.2c-.2.2-.3.2-.6.1-.3-.2-1.3-.5-2.4-1.5-.9-.8-1.5-1.8-1.7-2.1-.2-.3 0-.5.1-.7.1-.1.3-.3.4-.5.1-.2.2-.3.3-.5.1-.2 0-.4 0-.5-.1-.2-.7-1.7-.9-2.3-.3-.6-.5-.5-.7-.5h-.6c-.2 0-.5.1-.8.4s-1 1-1 2.5 1.1 2.9 1.2 3.1c.1.2 2.1 3.2 5.1 4.5.7.3 1.3.5 1.7.6.7.2 1.4.2 1.9.1.6-.1 1.8-.7 2-1.4.3-.7.3-1.3.2-1.4-.1-.1-.3-.2-.5-.3zM12 2C6.5 2 2 6.5 2 12c0 1.8.5 3.5 1.3 5L2 22l5.2-1.4c1.4.8 3.1 1.2 4.8 1.2 5.5 0 10-4.5 10-10S17.5 2 12 2zm0 18.3c-1.5 0-3-.4-4.3-1.2l-.3-.2-3.2.8.9-3.1-.2-.3C4.1 15 3.7 13.5 3.7 12 3.7 7.4 7.4 3.7 12 3.7s8.3 3.7 8.3 8.3-3.7 8.3-8.3 8.3z"/></svg>`;
    case 'viber':
      return `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C7 2 3 5.6 3 10c0 1.6.5 3.1 1.4 4.3-.2.8-.6 2.2-.7 2.6 0 .2.1.4.4.4.1 0 .2 0 .3-.1.4-.2 1.8-.9 2.4-1.2 1.5.6 3.2.9 5.2.9 5 0 9-3.6 9-8s-4-8-9-8zm-2 4.3c.4-.3 1-.2 1.5.2.5.3 1.7 1.6 2 2.1.3.4.3.9.1 1.2-.2.2-.5.4-.6.5-.1.1 0 .3.1.4.4.6.9 1.1 1.5 1.6.5.3.9.5 1.2.6.1 0 .3 0 .4-.1l.5-.6c.3-.3.7-.3 1.1 0 .4.3 1.7 1.4 2.1 1.8.4.4.4 1 .1 1.4-.3.4-1 1-1.4 1-.4.1-.9.1-2.8-.7-1.9-.8-3.7-2.5-4.7-3.6-1-1.1-2-2.5-2.4-3.6-.4-1.2-.4-1.7-.3-2.1.1-.4.7-1 .9-1.1z"/></svg>`;
    case 'telegram':
      return `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M22 3 2 11l6 2 2 7 4-4 6 5 2-18zM10 14l8-7-10 9 2-2z"/></svg>`;
    case 'line':
      return `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3C6.5 3 2 6.7 2 11.2c0 4 3.6 7.4 8.5 8 .3.1.7.2.9.5.1.2.1.5.1.8l-.1.9c0 .3-.2 1 .9.6 1.1-.5 6-3.5 8.2-6.1C22.1 14.2 23 12.8 23 11.2 23 6.7 18 3 12 3zM8 13.5H6V9.5c0-.3.2-.5.5-.5s.5.2.5.5v3h1c.3 0 .5.2.5.5s-.2.5-.5.5zm2-.5c0 .3-.2.5-.5.5s-.5-.2-.5-.5V9.5c0-.3.2-.5.5-.5s.5.2.5.5V13zm5 0c0 .2-.1.4-.3.5-.1 0-.1.1-.2.1-.2 0-.3-.1-.4-.2l-2-2.7V13c0 .3-.2.5-.5.5s-.5-.2-.5-.5V9.5c0-.2.1-.4.3-.5.2-.1.5 0 .6.2l2 2.7V9.5c0-.3.2-.5.5-.5s.5.2.5.5v3.5zm3 0H16c-.3 0-.5-.2-.5-.5V9.5c0-.3.2-.5.5-.5h2c.3 0 .5.2.5.5s-.2.5-.5.5h-1.5v.8H18c.3 0 .5.2.5.5s-.2.5-.5.5h-1.5v.8H18c.3 0 .5.2.5.5s-.2.5-.5.5z"/></svg>`;
    case 'wechat':
      return `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8.7 8.5c-.5 0-.9.3-.9.8s.4.8.9.8.9-.3.9-.8-.4-.8-.9-.8zm4.6 0c-.5 0-.9.3-.9.8s.4.8.9.8.9-.3.9-.8-.4-.8-.9-.8zm-2.3-5C5.7 3.5 2 6.7 2 10.5c0 2.1 1.2 4 3 5.3l-.5 2.2 2.6-1.5c.8.2 1.6.3 2.4.3.2 0 .5 0 .7-.1-.2-.6-.3-1.2-.3-1.8 0-3.5 3.2-6.3 7.2-6.3.5 0 1 .1 1.5.1-.7-2.9-3.8-5.2-7.6-5.2zm6.6 6c-3.3 0-6 2.5-6 5.5s2.7 5.5 6 5.5c.6 0 1.3-.1 1.9-.3l1.9 1.1-.4-1.7c1.4-1 2.4-2.5 2.4-4.1 0-3-2.7-5.5-5.8-5.5h-.1zm-2 3c-.4 0-.7.2-.7.6 0 .4.3.6.7.6s.7-.2.7-.6c0-.4-.3-.6-.7-.6zm3.6 0c-.4 0-.7.2-.7.6 0 .4.3.6.7.6s.7-.2.7-.6c0-.4-.3-.6-.7-.6z"/></svg>`;
    case 'signal':
      return `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.5 2 2 6.5 2 12c0 1.6.4 3.2 1.1 4.5L2 22l5.5-1.1c1.3.7 2.9 1.1 4.5 1.1 5.5 0 10-4.5 10-10S17.5 2 12 2zm0 2c4.4 0 8 3.6 8 8s-3.6 8-8 8c-1.4 0-2.8-.4-4-1l-3 .6.6-3c-.6-1.2-1-2.6-1-4 0-4.4 3.6-8 8-8z"/></svg>`;
    case 'zalo':
      return `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6 2 2 5.8 2 10.3c0 2.4 1.3 4.6 3.4 6.1L4.5 20l3.7-2c1.2.3 2.5.5 3.8.5 6 0 10-3.8 10-8.3S18 2 12 2zm-3.5 9.5H6v-4h.8v3.2h1.7v.8zm1.5 0h-.8v-4H10v4zm3.5 0h-.8L11 9.2v2.3h-.7v-4h.8l1.7 2.3V7.5h.7v4zm3.4 0h-2.5v-4h2.4v.7h-1.7v.9h1.6v.7h-1.6v1h1.8v.7z"/></svg>`;
  }
}
