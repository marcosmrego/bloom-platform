// Detecta o tenant — prioridade: env var BLOOM_TENANT > hostname > fallback
export function getTenantFromHost(host: string): string {
  // Se BLOOM_TENANT estiver definida, usa ela (modo multi-instância no Coolify)
  const envTenant = typeof process !== 'undefined' && process.env?.BLOOM_TENANT;
  if (envTenant) return envTenant;

  // Fallback: detecção por hostname (modo single-instance multi-domínio)
  const tenantMap: Record<string, string> = {
    'viralbarato.com.br': 'viralbarato',
    'www.viralbarato.com.br': 'viralbarato',
    'mundonoprato.com.br': 'mundonoprato',
    'www.mundonoprato.com.br': 'mundonoprato',
  };
  return tenantMap[host] || 'viralbarato';
}
