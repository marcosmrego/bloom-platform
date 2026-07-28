// Detecta o tenant — prioridade: env var BLOOM_TENANT > hostname > fallback
// ATENÇÃO: usa process.env (Node.js runtime), NÃO import.meta.env (build-time)
export function getTenantFromHost(host: string): string {
  // Modo multi-instância: variável de ambiente definida no container
  try {
    const envTenant = process.env.BLOOM_TENANT;
    if (envTenant && envTenant.length > 2) return envTenant;
  } catch (_) {
    // process pode não existir em edge/static
  }

  // Fallback: detecção por hostname
  const tenantMap: Record<string, string> = {
    'viralbarato.com.br': 'viralbarato',
    'www.viralbarato.com.br': 'viralbarato',
    'mundonoprato.com.br': 'mundonoprato',
    'www.mundonoprato.com.br': 'mundonoprato',
  };
  return tenantMap[host] || 'viralbarato';
}