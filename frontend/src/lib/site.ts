export interface SiteConfig {
  name: string;
  title: string;
  description: string;
  heading: string;
  subtitle: string;
  footer: string;
  accent: string;
  contentLabel: string;
  contentLabelPlural: string;
  placeholderImg: string;
  categoryPlaceholders: Record<string, string>;
}

const sites: Record<string, SiteConfig> = {
  viralbarato: {
    name: 'ViralBarato',
    title: 'ViralBarato — Reviews e Menores Preços',
    description: 'Descubra produtos com melhor custo-benefício. Reviews reais e links diretos para comprar.',
    heading: '🔥 ViralBarato',
    subtitle: 'Reviews honestas. Links diretos. Menor preço.',
    footer: '© 2026 ViralBarato. Links de afiliado Amazon.',
    accent: '#e63946',
    contentLabel: 'review',
    contentLabelPlural: 'reviews',
    placeholderImg: 'https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?w=800&fit=crop',
    categoryPlaceholders: {
      eletronicos: 'https://images.unsplash.com/photo-1468495244123-6c6c332eeece?w=800&fit=crop',
      beleza: 'https://images.unsplash.com/photo-1522335789203-aabd35475b56?w=800&fit=crop',
      'casa-cozinha': 'https://images.unsplash.com/photo-1556909114-f6e7ad7c22f2?w=800&fit=crop',
      esportes: 'https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&fit=crop',
      pets: 'https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=800&fit=crop',
    },
  },
  mundonoprato: {
    name: 'Mundo no Prato',
    title: 'Mundo no Prato — Gastronomia Mundial',
    description: 'Receitas, histórias e sabores de todos os cantos do planeta. Do Mediterrâneo à Ásia.',
    heading: '🌍 Mundo no Prato',
    subtitle: 'Receitas, ingredientes e histórias da gastronomia mundial.',
    footer: '© 2026 Mundo no Prato. Gastronomia sem fronteiras.',
    accent: '#c7512e',
    contentLabel: 'artigo',
    contentLabelPlural: 'artigos',
    placeholderImg: 'https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=800&fit=crop',
    categoryPlaceholders: {
      receitas: 'https://images.unsplash.com/photo-1547592180-85f173990554?w=800&fit=crop',
      historias: 'https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=800&fit=crop',
      ingredientes: 'https://images.unsplash.com/photo-1542838132-92c53300491e?w=800&fit=crop',
      utensilios: 'https://images.unsplash.com/photo-1556911220-bff31c812dba?w=800&fit=crop',
    },
  },
};

export function getSiteConfig(tenant: string): SiteConfig {
  const config = sites[tenant];
  if (!config) {
    throw new Error(`Tenant sem configuração visual: ${tenant}`);
  }
  return config;
}

export function getPostImage(
  config: SiteConfig,
  post: { image_url?: string | null; product_image?: string | null; category_slug?: string | null },
): string {
  return post.image_url
    || post.product_image
    || config.categoryPlaceholders[post.category_slug || '']
    || config.placeholderImg;
}
