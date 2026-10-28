export type Marketplace = 'amazon' | 'mercadolivre';

const MERCADOLIVRE_SHORT_HOST = 'meli.la';
const MERCADOLIVRE_DOMAIN = 'mercadolivre.com.br';

/** Posts created before Mercado Livre support only have Amazon links. */
export function marketplaceFromUrl(url?: string | null): Marketplace {
  try {
    const host = new URL(url ?? '').hostname;
    if (host === MERCADOLIVRE_SHORT_HOST || host === MERCADOLIVRE_DOMAIN || host.endsWith(`.${MERCADOLIVRE_DOMAIN}`)) {
      return 'mercadolivre';
    }
  } catch {
    // Not a valid URL: keep the legacy default.
  }
  return 'amazon';
}

const STORE_NAMES: Record<Marketplace, string> = {
  amazon: 'na Amazon',
  mercadolivre: 'no Mercado Livre',
};

export function buyLabel(marketplace: Marketplace, linkType?: string | null): string {
  const store = STORE_NAMES[marketplace];
  if (linkType === 'search') return `🔎 Ver opções ${store}`;
  if (linkType === 'offer') return `🏷️ Conferir oferta ${store}`;
  return `🛒 Ver preço ${store}`;
}

export function affiliateDisclosure(marketplace: Marketplace): string {
  return marketplace === 'mercadolivre'
    ? 'Como participante do Programa de Afiliados do Mercado Livre, podemos receber comissão por compras qualificadas.'
    : 'Como participante do Programa de Associados da Amazon, podemos receber comissão por compras qualificadas.';
}
