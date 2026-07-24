#!/usr/bin/env python3
"""
Seed inicial — Categorias e produtos para os tenants existentes.
"""
import sys
sys.path.insert(0, "/opt/data/bloom/api")
from main import get_db, DB_CONFIG
import psycopg2.extras

db = get_db()
cur = db.cursor()

# ── ViralBarato ────────────────────────────────────
cur.execute("SELECT id FROM tenants WHERE slug='viralbarato'")
vb_id = cur.fetchone()["id"]

vb_cats = [
    ("Eletrônicos", "eletronicos"),
    ("Casa & Cozinha", "casa-cozinha"),
    ("Beleza", "beleza"),
    ("Esportes", "esportes"),
    ("Pets", "pets"),
]

for name, slug in vb_cats:
    cur.execute(
        "INSERT INTO categories (tenant_id, name, slug) VALUES (%s,%s,%s) ON CONFLICT (tenant_id, slug) DO NOTHING",
        (vb_id, name, slug)
    )

# Produtos ViralBarato (ASINs reais da Amazon Brasil)
vb_products = [
    # Eletrônicos
    ("B09B8VGCR8", "Echo Dot 5ª Geração", "Caixa inteligente Alexa", 249.00, "eletronicos"),
    ("B0CJ5FXV7Z", "Kindle 11ª Geração", "Leitor digital 6 polegadas", 349.00, "eletronicos"),
    ("B0C6BQW5YN", "Fone JBL Tune 520BT", "Bluetooth 57h bateria", 149.90, "eletronicos"),
    ("B09YDCK2BN", "Carregador Ugreen 65W GaN", "Carregador rápido USB-C", 89.90, "eletronicos"),
    ("B0BSLJPY4G", "Fone Xiaomi Redmi Buds 4", "TWS cancelamento ruído", 199.00, "eletronicos"),
    # Casa & Cozinha
    ("B07WFHZQ2T", "Air Fryer Mondial AF-30 4L", "Fritadeira elétrica", 249.90, "casa-cozinha"),
    ("B09KMJYGJ8", "Liquidificador Mondial L-99", "3 velocidades 2L", 89.90, "casa-cozinha"),
    ("B0B5Y8FG89", "Panela de Pressão Elétrica 4L", "Mondial timer digital", 219.90, "casa-cozinha"),
    ("B08XYZ1234", "Jogo de Facas Tramontina", "6 peças aço inox", 79.90, "casa-cozinha"),
    # Beleza
    ("B08XYZ5678", "Secador Taiff Style 2000W", "Profissional 2 velocidades", 119.90, "beleza"),
    ("B07XYZ9999", "Balança Digital Vidro", "180kg LED azul", 39.90, "beleza"),
    # Esportes
    ("B08XYZ1111", "Tapete Yoga 6mm TPE", "Antiderrapante ecológico", 59.90, "esportes"),
    ("B09XYZ2222", "Halteres Emborrachados 10kg", "Par anilhas", 149.90, "esportes"),
    # Pets
    ("B08XYZ3333", "Bebedouro Automático Pet", "Fonte 2.5L filtro carvão", 79.90, "pets"),
    ("B09XYZ4444", "Brinquedo Kong Médio", "Cães médios resistente", 49.90, "pets"),
]

# Resolver category_id e inserir produtos
for asin, title, desc, price, cat_slug in vb_products:
    cur.execute("SELECT id FROM categories WHERE tenant_id=%s AND slug=%s", (vb_id, cat_slug))
    cat = cur.fetchone()
    cat_id = cat["id"] if cat else None
    cur.execute("""
        INSERT INTO products (tenant_id, asin, title, description, price, category_id)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (tenant_id, asin) DO UPDATE SET title=EXCLUDED.title, price=EXCLUDED.price
    """, (vb_id, asin, title, desc, price, cat_id))
    # Marcar ASIN como placeholder se for fictício
    if "XYZ" in asin:
        cur.execute("UPDATE products SET active=false WHERE tenant_id=%s AND asin=%s", (vb_id, asin))

print(f"ViralBarato: {len(vb_products)} produtos inseridos")

# ── Mundo no Prato ──────────────────────────────────
cur.execute("SELECT id FROM tenants WHERE slug='mundonoprato'")
mp_id = cur.fetchone()["id"]

mp_cats = [
    ("Receitas", "receitas"),
    ("Histórias", "historias"),
    ("Utensílios", "utensilios"),
    ("Ingredientes", "ingredientes"),
]

for name, slug in mp_cats:
    cur.execute(
        "INSERT INTO categories (tenant_id, name, slug) VALUES (%s,%s,%s) ON CONFLICT (tenant_id, slug) DO NOTHING",
        (mp_id, name, slug)
    )

mp_products = [
    # Utensílios
    ("B07XYZ7777", "Faca do Chef Tramontina 8''", "Aço inox Century", 89.90, "utensilios"),
    ("B08XYZ8888", "Panela de Ferro Fundido 26cm", "Pré-temperada", 129.90, "utensilios"),
    ("B09XYZ9999", "Kit 3 Panelas Antiaderentes", "Tramontina Turim", 159.90, "utensilios"),
    # Ingredientes
    ("B08XYZ0000", "Azeite Extra Virgem Gallo 500ml", "Português premium", 34.90, "ingredientes"),
    ("B09XYZ1110", "Kit Especiarias 12 potes", "Temperos premium", 49.90, "ingredientes"),
]

for asin, title, desc, price, cat_slug in mp_products:
    cur.execute("SELECT id FROM categories WHERE tenant_id=%s AND slug=%s", (mp_id, cat_slug))
    cat = cur.fetchone()
    cat_id = cat["id"] if cat else None
    cur.execute("""
        INSERT INTO products (tenant_id, asin, title, description, price, category_id)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (tenant_id, asin) DO UPDATE SET title=EXCLUDED.title, price=EXCLUDED.price
    """, (mp_id, asin, title, desc, price, cat_id))

print(f"Mundo no Prato: {len(mp_products)} produtos inseridos")

db.commit()
cur.close()
db.close()
print("✅ Seed concluído!")
