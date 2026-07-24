#!/usr/bin/env python3
"""
Cria um novo blog na plataforma Bloom em minutos.

Uso:
  python3 create_blog.py --name "TênisBarato" --slug tenisbarato --domain tenisbarato.com.br --niche "tênis"

O que faz:
  1. Insere tenant no banco
  2. Cria categorias padrão
  3. Gera arquivo .env com config do blog
  4. Mostra instruções para DNS Cloudflare + Coolify
"""
import sys, os, argparse
sys.path.insert(0, "/opt/data/bloom/api")

DEFAULT_CATEGORIES = [
    # Blog de reviews
    [
        ("Eletrônicos", "eletronicos"),
        ("Casa & Cozinha", "casa-cozinha"),
        ("Beleza", "beleza"),
        ("Esportes", "esportes"),
        ("Pets", "pets"),
    ],
    # Blog de conteúdo (receitas, etc)
    [
        ("Artigos", "artigos"),
        ("Guias", "guias"),
        ("Reviews", "reviews"),
        ("Dicas", "dicas"),
    ],
    # Blog de nicho específico (tênis, etc)
    [
        ("Reviews", "reviews"),
        ("Comparativos", "comparativos"),
        ("Lançamentos", "lancamentos"),
        ("Guias", "guias"),
    ],
]

def main():
    parser = argparse.ArgumentParser(description="Criar novo blog na plataforma Bloom")
    parser.add_argument("--name", required=True, help="Nome do blog (ex: TênisBarato)")
    parser.add_argument("--slug", required=True, help="Slug URL (ex: tenisbarato)")
    parser.add_argument("--domain", required=True, help="Domínio (ex: tenisbarato.com.br)")
    parser.add_argument("--niche", default="reviews", help="Nicho (reviews, conteudo, especifico)")
    parser.add_argument("--amazon-tag", default="marcosmrego-20", help="Tag Amazon Afiliados")
    parser.add_argument("--cat-template", type=int, default=0, help="Template de categorias (0=reviews, 1=conteudo, 2=especifico)")
    args = parser.parse_args()

    # Conectar ao banco
    from main import get_db
    conn = get_db()
    cur = conn.cursor()

    # Inserir tenant
    cur.execute("""
        INSERT INTO tenants (slug, name, domain, niche, monetization)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name
        RETURNING id
    """, (args.slug, args.name, args.domain, args.niche,
          f'{{"amazon_tag": "{args.amazon_tag}"}}'))
    tenant_id = cur.fetchone()["id"]
    conn.commit()

    print(f"✅ Tenant criado: {args.name} (ID: {tenant_id})")

    # Criar categorias
    cats = DEFAULT_CATEGORIES[min(args.cat_template, 2)]
    for name, slug in cats:
        cur.execute(
            "INSERT INTO categories (tenant_id, name, slug) VALUES (%s,%s,%s) ON CONFLICT (tenant_id, slug) DO NOTHING",
            (tenant_id, name, slug)
        )
    conn.commit()
    print(f"✅ {len(cats)} categorias criadas: {', '.join(c[1] for c in cats)}")

    cur.close()
    conn.close()

    # Instruções
    print(f"""
╔══════════════════════════════════════════════════════════╗
║  BLOG CRIADO COM SUCESSO!                               ║
╠══════════════════════════════════════════════════════════╣
║  Nome:    {args.name:<44} ║
║  Slug:    {args.slug:<44} ║
║  Domínio: {args.domain:<44} ║
╠══════════════════════════════════════════════════════════╣
║  PRÓXIMOS PASSOS:                                       ║
║                                                         ║
║  1. DNS Cloudflare:                                     ║
║     CNAME {args.domain} -> bloom.expansao-ai.com.br     ║
║                                                         ║
║  2. Adicionar produtos:                                 ║
║     INSERT INTO products (tenant_id, asin, ...)         ║
║                                                         ║
║  3. Gerar primeiro post:                                ║
║     curl -X POST .../api/v1/{args.slug}/posts           ║
║                                                         ║
║  4. Configurar AdSense (se tiver):                      ║
║     UPDATE tenants SET monetization = ...               ║
╚══════════════════════════════════════════════════════════╝
""")

if __name__ == "__main__":
    main()
