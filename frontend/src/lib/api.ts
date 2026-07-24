// Cliente da API Bloom
const API_BASE = process.env.BLOOM_API || 'http://localhost:8000';

interface Post {
  id: number;
  title: string;
  slug: string;
  excerpt: string | null;
  content?: string;
  image_url: string | null;
  rating: number | null;
  tags: string[] | null;
  status: string;
  published_at: string;
  category_name: string | null;
  category_slug: string | null;
  product_title: string | null;
  product_price: number | null;
  affiliate_url: string | null;
  tenant_name?: string;
}

interface Category {
  id: number;
  name: string;
  slug: string;
}

export async function getPosts(tenant: string, category?: string): Promise<Post[]> {
  const url = new URL(`/api/v1/${tenant}/posts`, API_BASE);
  if (category) url.searchParams.set('category', category);
  url.searchParams.set('page_size', '50');
  const res = await fetch(url.toString());
  if (!res.ok) return [];
  const data = await res.json();
  return data.items;
}

export async function getPost(tenant: string, slug: string): Promise<Post | null> {
  const res = await fetch(`${API_BASE}/api/v1/${tenant}/posts/${slug}`);
  if (!res.ok) return null;
  return res.json();
}

export async function getCategories(tenant: string): Promise<Category[]> {
  const res = await fetch(`${API_BASE}/api/v1/${tenant}/categories`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.items;
}

export async function registerClick(
  tenant: string,
  productId: number,
  postId: number,
  sourceUrl: string,
) {
  try {
    await fetch(`${API_BASE}/api/v1/${tenant}/clicks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId, post_id: postId, link_type: 'amazon', source_url: sourceUrl }),
    });
  } catch { /* fire and forget */ }
}
