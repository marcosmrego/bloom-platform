import type { APIRoute } from 'astro';

const allowedPath = /^(?:metrics|agent-reviews\/metrics|revenue\/import|posts(?:\/\d+(?:\/decision)?)?|monetization\/proposals(?:\/\d+\/decision)?)$/;

const proxy: APIRoute = async ({ params, request }) => {
  const path = params.path || '';
  if (!allowedPath.test(path)) {
    return new Response(JSON.stringify({ detail: 'Unsupported editorial route' }), {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const token = process.env.REVIEW_API_TOKEN || '';
  if (!token) {
    return new Response(JSON.stringify({ detail: 'Review API is not configured' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const apiBase = process.env.BLOOM_API || 'http://localhost:8000';
  const upstream = new URL(`/api/v1/editorial/review/${path}`, apiBase);
  upstream.search = new URL(request.url).search;

  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    Accept: 'application/json',
  };
  const contentType = request.headers.get('content-type');
  if (contentType) headers['Content-Type'] = contentType;

  const init: RequestInit = { method: request.method, headers };
  if (!['GET', 'HEAD'].includes(request.method)) {
    init.body = await request.text();
  }

  try {
    const response = await fetch(upstream, init);
    return new Response(response.body, {
      status: response.status,
      headers: {
        'Content-Type': response.headers.get('content-type') || 'application/json',
        'Cache-Control': 'no-store',
      },
    });
  } catch {
    return new Response(JSON.stringify({ detail: 'Editorial API is unavailable' }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    });
  }
};

export const GET = proxy;
export const PATCH = proxy;
export const POST = proxy;
