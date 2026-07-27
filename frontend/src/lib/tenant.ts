// Detecta o tenant a partir do domínio
export function getTenantFromHost(host: string): string {
  const tenantMap: Record<string, string> = {
    'viralbarato.com.br': 'viralbarato',
    'www.viralbarato.com.br': 'viralbarato',
    'mundonoprato.com.br': 'mundonoprato',
    'www.mundonoprato.com.br': 'mundonoprato',
  };
  return tenantMap[host] || 'viralbarato';
}
