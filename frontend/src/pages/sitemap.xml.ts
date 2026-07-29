import type { APIContext } from 'astro';
import { getCategories, getPosts } from '../lib/api';
import { getTenantFromHost } from '../lib/tenant';
import { getSiteConfig } from '../lib/site';

const escapeXml = (value: string) => value.replace(/[<>&'"]/g, char => ({
  '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;',
}[char]!));

export async function GET({ url }: APIContext) {
  const tenant = getTenantFromHost(url.hostname);
  const config = getSiteConfig(tenant);
  const [posts, categories] = await Promise.all([getPosts(tenant), getCategories(tenant)]);
  const base = `https://${config.domain}`;
  const entries = [
    { loc: `${base}/`, lastmod: posts[0]?.updated_at || posts[0]?.published_at },
    ...categories.map(category => ({ loc: `${base}/categoria/${encodeURIComponent(category.slug)}`, lastmod: undefined })),
    ...posts.map(post => ({ loc: `${base}/blog/${encodeURIComponent(post.slug)}`, lastmod: post.updated_at || post.published_at })),
    ...['sobre', 'contato', 'privacidade', 'termos'].map(path => ({ loc: `${base}/${path}`, lastmod: undefined })),
  ];
  const body = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${entries.map(entry =>
    `  <url><loc>${escapeXml(entry.loc)}</loc>${entry.lastmod ? `<lastmod>${new Date(entry.lastmod).toISOString()}</lastmod>` : ''}</url>`
  ).join('\n')}\n</urlset>\n`;
  return new Response(body, { headers: { 'Content-Type': 'application/xml; charset=utf-8', 'Cache-Control': 'public, max-age=900' } });
}
