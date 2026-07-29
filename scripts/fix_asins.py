"""
Corrige ASINs dos produtos e vincula posts aos produtos no banco Bloom.
Lê os ASINs reais dos markdowns do ViralBarato.
"""
import os, re, yaml, psycopg2
from db_config import get_db_config, get_tenant_id

DB = get_db_config()

def extract_asin(url):
    m = re.search(r'/dp/([A-Z0-9]{10})', url)
    return m.group(1) if m else None

def extract_product_name(meta):
    """Extrai nome do produto do frontmatter."""
    name = meta.get('productName', '') or meta.get('title', '')
    # Remove sufixos comuns
    for suffix in [' — Vale a Pena? Review', ' — Review', ' — Vale a Pena?', ' [2026]']:
        name = name.replace(suffix, '')
    return name.strip()

# 1. Extrair ASINs dos markdowns
blog_dir = '/opt/data/viralbarato/src/content/blog'
post_asins = {}  # slug → asin

for root, dirs, files in os.walk(blog_dir):
    for f in files:
        if not f.endswith('.md'):
            continue
        path = os.path.join(root, f)
        with open(path) as fh:
            raw = fh.read()
        
        if not raw.startswith('---'):
            continue
        parts = raw.split('---', 2)
        if len(parts) < 3:
            continue
        
        try:
            meta = yaml.safe_load(parts[1])
        except:
            continue
        
        product_name = extract_product_name(meta)
        
        asin = None
        links = meta.get('affiliateLinks', [])
        for link in links:
            if 'amazon' in link.get('url', '').lower():
                asin = extract_asin(link['url'])
                break
        
        if asin and product_name:
            post_asins[product_name] = asin
            print(f'  {asin:12s} ← {product_name[:60]}')

print(f'\n{len(post_asins)} produtos com ASIN extraídos')

# 2. Conectar ao banco e atualizar
conn = psycopg2.connect(**DB)
cur = conn.cursor()
tenant_id = get_tenant_id(cur)

# Buscar todos os produtos do ViralBarato
cur.execute('SELECT id, asin, title FROM products WHERE tenant_id=%s', (tenant_id,))
products = {r[2].lower(): (r[0], r[1], r[2]) for r in cur.fetchall()}

updated_asins = 0
matched = 0

for prod_name, asin in post_asins.items():
    # Buscar produto por nome (case insensitive, partial match)
    found = None
    for key, (pid, old_asin, title) in products.items():
        # Tenta match exato ou parcial
        if prod_name.lower() == key:
            found = (pid, old_asin, title)
            break
        # Match parcial: produto contém nome ou vice-versa
        if prod_name.lower()[:20] in key or key[:20] in prod_name.lower():
            found = (pid, old_asin, title)
            break
    
    if found:
        pid, old_asin, title = found
        if old_asin != asin:
            cur.execute('UPDATE products SET asin=%s WHERE id=%s', (asin, pid))
            print(f'  UPDATE: {old_asin} → {asin} ({title})')
            updated_asins += 1
        matched += 1

conn.commit()
print(f'\nASINs atualizados: {updated_asins}, produtos com match: {matched}/{len(post_asins)}')

# 3. Vincular posts aos produtos pelo ASIN
cur.execute('SELECT id, slug, title FROM posts WHERE tenant_id=%s AND product_id IS NULL', (tenant_id,))
unlinked = cur.fetchall()
print(f'\nPosts sem produto: {len(unlinked)}')

linked = 0
for post_id, slug, title in unlinked:
    # Tentar achar o ASIN pelo nome do post
    for prod_name, asin in post_asins.items():
        # Match pelo título do post ou nome do produto
        if prod_name.lower()[:15] in title.lower() or title.lower()[:15] in prod_name.lower():
            # Achar product_id pelo ASIN
            cur.execute('SELECT id FROM products WHERE tenant_id=%s AND asin=%s', (tenant_id, asin))
            row = cur.fetchone()
            if row:
                cur.execute('UPDATE posts SET product_id=%s WHERE id=%s', (row[0], post_id))
                print(f'  LINK: {title[:50]} → {asin}')
                linked += 1
                break

conn.commit()
print(f'Posts vinculados: {linked}')

# 4. Verificar resultado
cur.execute('SELECT COUNT(*), COUNT(product_id) FROM posts WHERE tenant_id=%s', (tenant_id,))
total, with_product = cur.fetchone()
print(f'\nResultado: {with_product}/{total} posts com produto vinculado')

conn.close()
