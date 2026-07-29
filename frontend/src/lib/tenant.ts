// Detecta o tenant — prioridade: override explícito > hostname.
// ATENÇÃO: usa process.env (Node.js runtime), NÃO import.meta.env (build-time)
export function getTenantFromHost(host: string): string {
  // Modo de instância dedicada: variável definida explicitamente no deploy.
  try {
    const envTenant = process.env.BLOOM_TENANT?.trim().toLowerCase();
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
  const normalizedHost = host.toLowerCase().split(':')[0];
  const tenant = tenantMap[normalizedHost];
  if (!tenant) {
    throw new Error(`Host sem tenant configurado: ${host}`);
  }
  return tenant;
}
