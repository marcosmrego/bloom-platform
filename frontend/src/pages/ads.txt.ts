import type { APIContext } from 'astro';

export function GET({}: APIContext) {
  const client = process.env.ADSENSE_CLIENT_ID?.trim();
  const extra = process.env.ADS_TXT_EXTRA?.trim();
  const lines: string[] = [];
  if (client && /^ca-pub-\d+$/.test(client)) {
    lines.push(`google.com, ${client.replace(/^ca-/, '')}, DIRECT, f08c47fec0942fa0`);
  }
  if (extra) lines.push(...extra.split(/\r?\n/).map(line => line.trim()).filter(Boolean));
  return new Response(`${lines.join('\n')}${lines.length ? '\n' : ''}`, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'public, max-age=3600' },
  });
}

