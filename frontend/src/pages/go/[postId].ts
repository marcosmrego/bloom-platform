import { randomUUID } from 'node:crypto';
import type { APIRoute } from 'astro';
import { getPosts } from '../../lib/api';
import { getTenantFromHost } from '../../lib/tenant';

const attributionKeys = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'] as const;

export const GET: APIRoute = async ({ params, request, url, redirect }) => {
  const postId = Number(params.postId);
  if (!Number.isInteger(postId) || postId < 1) return redirect('/', 302);

  let tenant: string;
  try {
    tenant = getTenantFromHost(url.hostname);
  } catch {
    return redirect('/', 302);
  }

  const payload: Record<string, string | number | null> = {
    post_id: postId,
    session_id: url.searchParams.get('sid') || randomUUID(),
    source_url: request.headers.get('referer') || `${url.origin}/`,
    referrer: url.searchParams.get('referrer'),
  };
  for (const key of attributionKeys) payload[key] = url.searchParams.get(key);

  const apiBase = process.env.BLOOM_API || 'http://localhost:8000';
  try {
    const upstream = await fetch(`${apiBase}/api/v1/${tenant}/analytics/affiliate-click`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(payload),
    });
    if (upstream.ok) {
      const data = await upstream.json();
      if (typeof data.destination_url === 'string') return redirect(data.destination_url, 302);
    }
  } catch {
    // Keep the commerce path working if telemetry is temporarily unavailable.
  }

  const fallback = (await getPosts(tenant)).find((post) => post.id === postId)?.affiliate_url;
  return redirect(fallback || '/', 302);
};
