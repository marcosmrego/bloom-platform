// Cloudflare Worker — Proxy de Preço Amazon
addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request));
});

async function handleRequest(request) {
  const url = new URL(request.url);
  const asin = url.searchParams.get('asin');
  
  if (!asin || !/^[A-Z0-9]{10}$/.test(asin)) {
    return new Response(JSON.stringify({ error: 'ASIN inválido' }), {
      status: 400, headers: { 'Content-Type': 'application/json' }
    });
  }

  try {
    const price = await fetchAmazonPrice(asin);
    return new Response(JSON.stringify({ asin, price, success: true }), {
      headers: { 'Content-Type': 'application/json' }
    });
  } catch (e) {
    return new Response(JSON.stringify({ asin, price: null, error: e.message, success: false }), {
      status: 502, headers: { 'Content-Type': 'application/json' }
    });
  }
}

async function fetchAmazonPrice(asin) {
  const headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9',
    'Accept': 'text/html,application/xhtml+xml',
  };

  const resp = await fetch(`https://www.amazon.com.br/dp/${asin}`, { headers, redirect: 'follow' });
  const html = await resp.text();

  // 1. priceAmount
  let match = html.match(/<span[^>]*class="a-price-whole"[^>]*>([\d.]+)</);
  if (match) return parseFloat(match[1].replace(/\./g, ''));

  // 2. JSON-LD
  match = html.match(/"price":\s*"?(\d+[.,]\d+)"?/);
  if (match) return parseFloat(match[1].replace(',', '.'));

  // 3. corePrice
  match = html.match(/"corePrice_desktop"[^}]*"value":\s*([\d.]+)/);
  if (match) return parseFloat(match[1]);

  // 4. priceblock
  match = html.match(/priceblock_ourprice[^>]*>R\$\s*([\d.,]+)</);
  if (match) return parseFloat(match[1].replace(/\./g, '').replace(',', '.'));

  // 5. Qualquer R$
  match = html.match(/R\$\s*([\d.]+,\d{2})/);
  if (match) return parseFloat(match[1].replace(/\./g, '').replace(',', '.'));

  throw new Error('Preço não encontrado');
}