// Cliente da API Bloom
function getApiBase(): string {
  return process.env.BLOOM_API || 'http://localhost:8000';
}

export interface Post {
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
  price?: number | null;
  product_price: number | null;
  product_image: string | null;
  affiliate_url: string | null;
  commerce_link_type?: 'product' | 'search' | 'offer' | null;
  coupon_code?: string | null;
  offer_text?: string | null;
  offer_valid_until?: string | null;
  offer_verified_at?: string | null;
  tenant_name?: string;
  seo_title?: string | null;
  seo_description?: string | null;
  updated_at?: string | null;
}

export interface Category {
  id: number;
  name: string;
  slug: string;
}

export async function getPosts(tenant: string, category?: string): Promise<Post[]> {
  const url = new URL(`/api/v1/${tenant}/posts`, getApiBase());
  if (category) url.searchParams.set('category', category);
  url.searchParams.set('page_size', '50');
  const res = await fetch(url.toString());
  if (!res.ok) return [];
  const data = await res.json();
  return data.items;
}

export async function getPost(tenant: string, slug: string): Promise<Post | null> {
  const res = await fetch(`${getApiBase()}/api/v1/${encodeURIComponent(tenant)}/posts/${encodeURIComponent(slug)}`);
  if (!res.ok) return null;
  return res.json();
}

export async function getCategories(tenant: string): Promise<Category[]> {
  const res = await fetch(`${getApiBase()}/api/v1/${tenant}/categories`);
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
    const base = getApiBase();
    await fetch(`${base}/api/v1/${tenant}/clicks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId, post_id: postId, link_type: 'amazon', source_url: sourceUrl }),
    });
  } catch { /* fire and forget */ }
}
