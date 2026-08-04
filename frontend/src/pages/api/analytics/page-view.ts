import type { APIRoute } from 'astro';
import { getTenantFromHost } from '../../../lib/tenant';

export const POST: APIRoute = async ({ request, url }) => {
  let tenant: string;
  try {
    tenant = getTenantFromHost(url.hostname);
  } catch {
    return new Response(null, { status: 404 });
  }

  const apiBase = process.env.BLOOM_API || 'http://localhost:8000';
  try {
    const upstream = await fetch(`${apiBase}/api/v1/${tenant}/analytics/page-view`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: await request.text(),
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
    });
  } catch {
    return new Response(JSON.stringify({ detail: 'Analytics unavailable' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
    });
  }
};
