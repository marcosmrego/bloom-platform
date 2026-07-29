import type { APIContext } from 'astro';
import { getTenantFromHost } from '../lib/tenant';
import { getSiteConfig } from '../lib/site';

export function GET({ url }: APIContext) {
  const config = getSiteConfig(getTenantFromHost(url.hostname));
  const body = `User-agent: *\nAllow: /\n\nSitemap: https://${config.domain}/sitemap.xml\n`;
  return new Response(body, { headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'public, max-age=3600' } });
}

