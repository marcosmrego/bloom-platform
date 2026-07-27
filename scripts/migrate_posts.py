"""
Migra posts dos blogs antigos (Astro SSG) para a plataforma Bloom via API.
"""
import os, re, yaml, json, urllib.request, sys, time

API_URL = "http://pw3vklu294cbqlk3ncpl9xez.212.85.22.227.sslip.io"

# Mapeamento de categorias do frontmatter → slugs do DB
CATEGORY_MAP = {
    "Eletrônicos": "eletronicos",
    "Eletronicos": "eletronicos",
    "Casa & Cozinha": "casa-cozinha",
    "Casa e Cozinha": "casa-cozinha",
    "Beleza": "beleza",
    "Esportes": "esportes",
    "Pets": "pets",
    "Top 10": "top10",
    "TOP 10": "top10",
    "Guias": "guias",
    # Mundo no Prato
    "ingredientes": "ingredientes",
    "receitas": "receitas",
    "histórias": "historias",
    "historias": "historias",
    "utensílios": "utensilios",
    "utensilios": "utensilios",
}

def api_post(path, data):
    """Faz POST para a API Bloom."""
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{API_URL}{path}", data=body,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        return {"error": err}, e.code

def extract_asin(url):
    """Extrai ASIN de URL Amazon."""
    m = re.search(r'/dp/([A-Z0-9]{10})', url)
    return m.group(1) if m else None

def parse_md(path):
    """Parse arquivo .md com frontmatter YAML."""
    with open(path) as f:
        raw = f.read()
    
    if not raw.startswith('---'):
        return None, None, raw
    
    parts = raw.split('---', 2)
    if len(parts) < 3:
        return None, None, raw
    
    try:
        meta = yaml.safe_load(parts[1])
    except:
        return None, None, raw
    
    content = parts[2].strip()
    
    # Remover fences markdown se existirem
    if content.startswith('```markdown\n'):
        content = content[len('```markdown\n'):]
    if content.startswith('```\n'):
        content = content[len('```\n'):]
    if content.endswith('\n```'):
        content = content[:-len('\n```')]
    elif content.endswith('```'):
        content = content[:-len('```')]
    
    return meta, parts[1], content.strip()

def migrate_viralbarato(blog_dir, dry_run=False):
    """Migra posts do ViralBarato."""
    blog_path = os.path.join(blog_dir, 'src/content/blog')
    files = []
    for root, dirs, filenames in os.walk(blog_path):
        for f in sorted(filenames):
            if f.endswith('.md'):
                files.append(os.path.join(root, f))
    
    results = {"ok": 0, "skip": 0, "error": 0, "posts": []}
    
    for filepath in files:
        rel = os.path.relpath(filepath, blog_path)
        meta, _, content = parse_md(filepath)
        
        if not meta:
            print(f"  SKIP {rel}: frontmatter inválido")
            results["skip"] += 1
            continue
        
        # Mapear categoria
        cat_name = meta.get('category', '')
        cat_slug = CATEGORY_MAP.get(cat_name, cat_name.lower().replace(' ', '-'))
        
        # Extrair ASIN do primeiro link Amazon
        asin = None
        links = meta.get('affiliateLinks', [])
        for link in links:
            if 'amazon' in link.get('url', '').lower():
                asin = extract_asin(link['url'])
                break
        
        # Extrair tags
        tags = meta.get('tags', [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',')]
        
        # Construir payload
        payload = {
            "tenant_slug": "viralbarato",
            "title": str(meta.get('title', '')),
            "content": content,
            "category_slug": cat_slug,
            "rating": meta.get('rating'),
            "pros": meta.get('pros', []),
            "cons": meta.get('cons', []),
            "tags": tags,
            "status": "published",
            "created_by": "hermes",
        }
        
        # Description → excerpt
        desc = meta.get('description', '')
        if desc and len(desc) > 10:
            payload["excerpt"] = desc
        
        # ASIN do produto
        if asin:
            payload["product_asin"] = asin
        
        if dry_run:
            status = "DRY RUN"
            print(f"  {status}: {rel} | cat={cat_slug} | asin={asin}")
            results["ok"] += 1
            results["posts"].append({"file": rel, "asin": asin, "cat": cat_slug})
        else:
            resp, code = api_post("/api/v1/viralbarato/posts", payload)
            if code in (200, 201):
                print(f"  OK: {rel} → {resp.get('slug', '?')}")
                results["ok"] += 1
            else:
                print(f"  ERRO {code}: {rel} → {resp.get('error', resp)}")
                results["error"] += 1
        
        time.sleep(0.5)  # Não sobrecarregar a API
    
    return results

def migrate_mundonoprato(blog_dir, dry_run=False):
    """Migra posts do Mundo no Prato."""
    blog_path = os.path.join(blog_dir, 'src/content/blog')
    files = []
    for root, dirs, filenames in os.walk(blog_path):
        for f in sorted(filenames):
            if f.endswith('.md'):
                files.append(os.path.join(root, f))
    
    results = {"ok": 0, "skip": 0, "error": 0, "posts": []}
    
    for filepath in files:
        rel = os.path.relpath(filepath, blog_path)
        meta, _, content = parse_md(filepath)
        
        if not meta:
            print(f"  SKIP {rel}: frontmatter inválido")
            results["skip"] += 1
            continue
        
        # Mapear categoria
        cat_name = meta.get('category', '').lower()
        cat_slug = CATEGORY_MAP.get(cat_name, cat_name.replace(' ', '-'))
        
        # heroImage
        hero = meta.get('heroImage', '')
        
        # Tags
        tags = meta.get('tags', [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',')]
        
        payload = {
            "tenant_slug": "mundonoprato",
            "title": str(meta.get('title', '')),
            "content": content,
            "category_slug": cat_slug,
            "tags": tags,
            "status": "published",
            "created_by": "hermes",
        }
        
        desc = meta.get('description', '')
        if desc and len(desc) > 10:
            payload["excerpt"] = desc
        
        if hero:
            payload["image_url"] = hero
        
        if dry_run:
            print(f"  DRY RUN: {rel} | cat={cat_slug} | img={'✓' if hero else '✗'}")
            results["ok"] += 1
        else:
            resp, code = api_post("/api/v1/mundonoprato/posts", payload)
            if code in (200, 201):
                print(f"  OK: {rel} → {resp.get('slug', '?')}")
                results["ok"] += 1
            else:
                print(f"  ERRO {code}: {rel} → {resp.get('error', resp)}")
                results["error"] += 1
        
        time.sleep(0.5)
    
    return results

if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    
    print(f"{'DRY RUN' if dry else 'MIGRAÇÃO REAL'} — ViralBarato")
    print("=" * 60)
    r1 = migrate_viralbarato("/opt/data/viralbarato", dry_run=dry)
    
    print(f"\n{'DRY RUN' if dry else 'MIGRAÇÃO REAL'} — Mundo no Prato")
    print("=" * 60)
    r2 = migrate_mundonoprato("/opt/data/mundonoprato", dry_run=dry)
    
    print(f"\n{'='*60}")
    print(f"ViralBarato: {r1['ok']} ok, {r1['skip']} skip, {r1['error']} erro")
    print(f"Mundo no Prato: {r2['ok']} ok, {r2['skip']} skip, {r2['error']} erro")
