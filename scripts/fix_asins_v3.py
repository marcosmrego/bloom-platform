"""V3: Vincula posts a produtos usando ASINs EXATOS dos markdowns originais."""
import os, re, yaml, psycopg2, unicodedata
from db_config import get_db_config, get_tenant_id

DB = get_db_config()

def extract_asin(url):
    m = re.search(r'/dp/([A-Z0-9]{10})', url)
    return m.group(1) if m else None

def normalize(s):
    return unicodedata.normalize('NFKD', s.lower()).encode('ascii','ignore').decode()

# 1. Extrair dados dos markdowns: título → {asin, price, prod_name}
blog_dir = '/opt/data/viralbarato/src/content/blog'
md_data = {}  # normalized_title → {asin, price, prod_name}

for root, dirs, files in os.walk(blog_dir):
    for f in files:
        if not f.endswith('.md'): continue
        path = os.path.join(root, f)
        with open(path) as fh: raw = fh.read()
        if not raw.startswith('---'): continue
        parts = raw.split('---', 2)
        if len(parts) < 3: continue
        try: meta = yaml.safe_load(parts[1])
        except: continue
        
        title = meta.get('title', '')
        prod_name = meta.get('productName', '') or title
        
        asin = None
        for link in meta.get('affiliateLinks', []):
            if 'amazon' in link.get('url','').lower():
                asin = extract_asin(link['url'])
                break
        
        if not asin: continue
        
        price_str = meta.get('productPrice', '')
        price_num = re.sub(r'[^0-9,]', '', str(price_str)).replace(',', '.')
        try: price = float(price_num)
        except: price = 0.0
        
        norm = normalize(title)
        md_data[norm] = {'asin': asin, 'price': price, 'prod_name': prod_name}

print(f'{len(md_data)} markdowns com ASIN')

# 2. Buscar posts e dar match exato por título normalizado
conn = psycopg2.connect(**DB)
cur = conn.cursor()
tenant_id = get_tenant_id(cur)
cur.execute('SELECT id, title FROM posts WHERE tenant_id=%s', (tenant_id,))
posts = [(r[0], r[1], normalize(r[1])) for r in cur.fetchall()]

linked = 0
errors = 0

for post_id, title, norm_title in posts:
    # Procurar nos markdowns por título
    best_key = None
    for key in md_data:
        if key == norm_title:
            best_key = key
            break
    
    if not best_key:
        # Tentar match parcial: remover sufixos e comparar
        clean = norm_title
        for s in [' vale a pena review', ' review completo', ' review e menor preco', 
                   ' review e melhor preco', ' review e onde comprar']:
            clean = clean.replace(s, '')
        clean = clean.strip()
        
        for key in md_data:
            clean_key = key
            for s in [' vale a pena review', ' review completo', ' review e menor preco',
                       ' review e melhor preco', ' review e onde comprar']:
                clean_key = clean_key.replace(s, '')
            if clean_key.strip() == clean:
                best_key = key
                break
    
    if not best_key:
        errors += 1
        continue
    
    data = md_data[best_key]
    asin = data['asin']
    price = data['price']
    prod_name = data['prod_name']
    
    # Achar ou criar produto pelo ASIN
    cur.execute('SELECT id, title, price FROM products WHERE tenant_id=%s AND asin=%s', (tenant_id, asin))
    row = cur.fetchone()
    
    if row:
        pid = row[0]
        # Atualizar nome e preço se necessário
        if price > 0 and (row[2] == 0 or row[2] is None):
            cur.execute('UPDATE products SET price=%s WHERE id=%s', (price, pid))
    else:
        # Criar produto
        clean_name = prod_name[:200]
        cur.execute(
            'INSERT INTO products (tenant_id, asin, title, price, active) VALUES (%s, %s, %s, %s, true) RETURNING id',
            (tenant_id, asin, clean_name, price)
        )
        pid = cur.fetchone()[0]
    
    # Vincular
    cur.execute('UPDATE posts SET product_id=%s WHERE id=%s', (pid, post_id))
    linked += 1
        print(f'  {title[:50]:50s} → {asin} R$ {price:.2f}')

conn.commit()
print(f'\nVinculados: {linked}, sem match: {errors}')

# Resultado
cur.execute('SELECT COUNT(*), COUNT(product_id) FROM posts WHERE tenant_id=%s', (tenant_id,))
total, with_prod = cur.fetchone()
print(f'{with_prod}/{total} posts com produto')

conn.close()
