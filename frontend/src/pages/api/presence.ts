import type { APIRoute } from 'astro';

const ACTIVE_WINDOW_MS = 75_000;
const ID_PATTERN = /^[a-f0-9-]{20,64}$/i;

type PresenceStore = Map<string, number>;

const globalPresence = globalThis as typeof globalThis & {
  bloomPresence?: PresenceStore;
};

const presence = globalPresence.bloomPresence ??= new Map<string, number>();

function activeCount(now = Date.now()) {
  for (const [visitorId, lastSeen] of presence) {
    if (now - lastSeen > ACTIVE_WINDOW_MS) presence.delete(visitorId);
  }
  return presence.size;
}

export const POST: APIRoute = async ({ request }) => {
  let visitorId = '';
  try {
    const body = await request.json();
    visitorId = typeof body?.visitorId === 'string' ? body.visitorId : '';
  } catch {
    // The validation response below also covers invalid JSON.
  }

  if (!ID_PATTERN.test(visitorId)) {
    return Response.json({ detail: 'Invalid visitor ID' }, { status: 400 });
  }

  const now = Date.now();
  presence.set(visitorId, now);
  return Response.json({ count: activeCount(now) }, {
    headers: { 'Cache-Control': 'no-store' },
  });
};
