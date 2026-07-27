"""V2: Cria produtos faltantes e vincula todos os posts."""
import os, re, yaml, psycopg2, unicodedata

DB = {
    'host': '212.85.22.227', 'port': 5432, 'dbname': 'bloom',
    'user': 'postgres', 'password': '2qS3CODTaQ42mgOYvgb5FKLp8906qTCb94vg5XQKziszz12O8lC6En2GJsW9qQ0q'
}

def extract_asin(url):
    m = re.search(r'/dp/([A-Z0-9]{10})', url)
    return m.group(1) if m else None

def normalize(s):
    return unicodedata.normalize('NFKD', s.lower()).encode('ascii', 'ignore').decode()

def extract_product_name(meta):
    name = meta.get('productName', '') or meta.get('title', '')
    for s in [' — Vale a Pena? Review', ' — Review', ' — Vale a Pena?', ' [2026]']:
        name = name.replace(s, '')
    return name.strip()

def words_match(a, b, min_words=2):
    """True se pelo menos min_words palavras batem."""
    wa = set(normalize(a).split())
    wb = set(normalize(b).split())
    common = wa & wb
    return len(common) >= min_words

conn = psycopg2.connect(**DB)
cur = conn.cursor()

# 1. Extrair ASINs + nomes dos markdowns
blog_dir = '/opt/data/viralbarato/src/content/blog'
post_data = {}  # filename → {name, asin, cat}

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
        
        prod_name = extract_product_name(meta)
        asin = None
        for link in meta.get('affiliateLinks', []):
            if 'amazon' in link.get('url', '').lower():
                asin = extract_asin(link['url'])
                break
        
        if asin:
            cat = meta.get('category', '')
            post_data[os.path.relpath(path, blog_dir)] = {
                'name': prod_name, 'asin': asin, 'cat': cat
            }

print(f'{len(post_data)} posts com ASIN')

# 2. Buscar produtos existentes
cur.execute('SELECT id, asin, title FROM products WHERE tenant_id=1')
products = [(r[0], r[1], r[2]) for r in cur.fetchall()]
print(f'{len(products)} produtos no DB')

# 3. Para cada post, achar ou criar produto
created = 0
updates = 0
links = 0

for filename, data in post_data.items():
    asin = data['asin']
    name = data['name']
    cat = data['cat']
    
    # Procurar produto por ASIN primeiro
    cur.execute('SELECT id, asin FROM products WHERE tenant_id=1 AND asin=%s', (asin,))
    row = cur.fetchone()
    
    if not row:
        # Procurar por nome
        best = None
        for pid, pasin, pname in products:
            if words_match(name, pname, 2):
                best = (pid, pasin)
                break
        
        if best:
            pid, old_asin = best
            if old_asin != asin:
                cur.execute('UPDATE products SET asin=%s WHERE id=%s', (asin, pid))
                updates += 1
        else:
            # Criar novo produto
            cat_slug_map = {'Eletrônicos':'eletronicos','Casa & Cozinha':'casa-cozinha',
                           'Casa e Cozinha':'casa-cozinha','Beleza':'beleza',
                           'Esportes':'esportes','Pets':'pets','TOP 10':'top10'}
            cat_slug = cat_slug_map.get(cat, 'eletronicos')
            cur.execute('SELECT id FROM categories WHERE tenant_id=1 AND slug=%s', (cat_slug,))
            crow = cur.fetchone()
            cat_id = crow[0] if crow else 1
            
            clean_name = name[:200]
            cur.execute(
                'INSERT INTO products (tenant_id, asin, title, category_id, price, active) VALUES (1, %s, %s, %s, 0, true) RETURNING id',
                (asin, clean_name, cat_id)
            )
            pid = cur.fetchone()[0]
            created += 1
    else:
        pid = row[0]
    
    # Vincular post ao produto
    # Achar o post pelo título aproximado
    norm_name = normalize(name)[:30]
    cur.execute("SELECT id FROM posts WHERE tenant_id=1 AND product_id IS NULL")
    for (post_id,) in cur.fetchall():
        # Já foi vinculado? Pular
        cur.execute('SELECT product_id FROM posts WHERE id=%s', (post_id,))
        if cur.fetchone()[0] is not None:
            continue
        
        cur.execute('SELECT title FROM posts WHERE id=%s', (post_id,))
        ptitle = cur.fetchone()[0]
        
        if words_match(name, ptitle, 2):
            cur.execute('UPDATE posts SET product_id=%s WHERE id=%s', (pid, post_id))
            links += 1
            break

conn.commit()

# Resultado final
cur.execute('SELECT COUNT(*), COUNT(product_id) FROM posts WHERE tenant_id=1')
total, with_prod = cur.fetchone()
cur.execute('SELECT COUNT(*) FROM products WHERE tenant_id=1')
prod_count = cur.fetchone()[0]

print(f'Criados: {created}, ASINs atualizados: {updates}, Posts vinculados: {links}')
print(f'Resultado: {with_prod}/{total} posts com produto, {prod_count} produtos no banco')

# Verificar affiliate_url
cur.execute("""SELECT p.slug, p.title, pr.asin, pr.price, 
    'https://www.amazon.com.br/dp/' || pr.asin || '?tag=marcosmrego-20' as affiliate_url
    FROM posts p JOIN products pr ON p.product_id=pr.id 
    WHERE p.tenant_id=1 LIMIT 3""")
for r in cur.fetchall():
    print(f'  {r[1][:40]} → {r[4]}')

conn.close()