import { timingSafeEqual } from 'node:crypto';
import { defineMiddleware } from 'astro:middleware';

function safeEqual(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);
  return leftBuffer.length === rightBuffer.length
    && timingSafeEqual(leftBuffer, rightBuffer);
}

export const onRequest = defineMiddleware(async (context, next) => {
  const path = context.url.pathname;
  if (!path.startsWith('/admin') && !path.startsWith('/api/editorial')) {
    return next();
  }

  const expectedUser = process.env.EDITORIAL_REVIEW_USER || 'editor';
  const expectedPassword = process.env.EDITORIAL_REVIEW_PASSWORD || '';
  if (!expectedPassword) {
    return new Response('Editorial review is not configured', { status: 503 });
  }

  const header = context.request.headers.get('authorization') || '';
  const encoded = header.startsWith('Basic ') ? header.slice(6) : '';
  let suppliedUser = '';
  let suppliedPassword = '';
  try {
    const decoded = Buffer.from(encoded, 'base64').toString('utf8');
    const separator = decoded.indexOf(':');
    suppliedUser = separator >= 0 ? decoded.slice(0, separator) : '';
    suppliedPassword = separator >= 0 ? decoded.slice(separator + 1) : '';
  } catch {
    // Invalid authorization is handled below.
  }

  if (
    !safeEqual(suppliedUser, expectedUser)
    || !safeEqual(suppliedPassword, expectedPassword)
  ) {
    return new Response('Authentication required', {
      status: 401,
      headers: {
        'WWW-Authenticate': 'Basic realm="Bloom Editorial", charset="UTF-8"',
        'Cache-Control': 'no-store',
      },
    });
  }

  const response = await next();
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Frame-Options', 'DENY');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
});
