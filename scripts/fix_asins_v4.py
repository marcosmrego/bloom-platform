import os, re, yaml, psycopg2, unicodedata

DB = {'host':'212.85.22.227','port':5432,'dbname':'bloom','user':'postgres','password':'2qS3CODTaQ42mgOYvgb5FKLp8906qTCb94vg5XQKziszz12O8lC6En2GJsW9qQ0q'}
conn = psycopg2.connect(**DB)
cur = conn.cursor()

def norm(s):
    return unicodedata.normalize('NFKD', s.lower()).encode('ascii','ignore').decode()

blog_dir = '/opt/data/viralbarato/src/content/blog'
md_asins = {}

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
        asin = None
        for link in meta.get('affiliateLinks', []):
            m = re.search(r'/dp/([A-Z0-9]{10})', link.get('url',''))
            if m: asin = m.group(1); break
        md_asins[path] = {'asin': asin, 'title': norm(meta.get('title',''))}

cur.execute('UPDATE posts SET product_id=NULL WHERE tenant_id=1')
cur.execute('SELECT id, slug, title FROM posts WHERE tenant_id=1')
posts = [(r[0], r[1], norm(r[2])) for r in cur.fetchall()]

linked = 0
for path, data in md_asins.items():
    asin = data['asin']
    if not asin: continue
    md_title = data['title']
    
    for post_id, slug, ptitle in posts:
        if ptitle == md_title:
            cur.execute('SELECT id FROM products WHERE tenant_id=1 AND asin=%s', (asin,))
            row = cur.fetchone()
            if not row:
                with open(path) as fh: raw = fh.read()
                meta = yaml.safe_load(raw.split('---', 2)[1])
                pname = meta.get('productName', meta.get('title',''))[:200]
                pstr = meta.get('productPrice', '0')
                pnum = float(re.sub(r'[^0-9,]', '', str(pstr)).replace(',', '.'))
                cur.execute('INSERT INTO products (tenant_id,asin,title,price,active) VALUES (1,%s,%s,%s,true) RETURNING id', (asin,pname,pnum))
                pid = cur.fetchone()[0]
            else:
                pid = row[0]
            cur.execute('UPDATE posts SET product_id=%s WHERE id=%s', (pid, post_id))
            linked += 1
            break

conn.commit()
cur.execute('SELECT COUNT(*), COUNT(product_id) FROM posts WHERE tenant_id=1')
total, with_prod = cur.fetchone()
print(f'Vinculados: {linked}')
print(f'Resultado: {with_prod}/{total}')

cur.execute('SELECT title FROM posts WHERE tenant_id=1 AND product_id IS NULL')
print('\nSEM ASIN:')
for r in cur.fetchall():
    print(f'  {r[0][:70]}')

# Verificar panelas
cur.execute("SELECT p.title, pr.title, pr.asin, pr.price FROM posts p LEFT JOIN products pr ON p.product_id=pr.id WHERE p.tenant_id=1 AND lower(p.title) LIKE '%panela%'")
print('\nVerificacao panelas:')
for r in cur.fetchall():
    prod = r[1] or 'N/A'
    asin = r[2] or ''
    print(f'  Post: {r[0][:50]}')
    print(f'  Prod: {prod[:40]} {asin} R$ {r[3]}')
    print()

conn.close()