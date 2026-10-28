import assert from 'node:assert/strict';
import { test } from 'node:test';
import { affiliateDisclosure, buyLabel, marketplaceFromUrl } from './marketplace.ts';

test('detects the marketplace from the affiliate URL', () => {
  assert.equal(marketplaceFromUrl('https://www.amazon.com.br/dp/B0ABCDE123?tag=x-20'), 'amazon');
  assert.equal(marketplaceFromUrl('https://meli.la/2AbCdEf'), 'mercadolivre');
  assert.equal(marketplaceFromUrl('https://produto.mercadolivre.com.br/MLB-3456789012-x'), 'mercadolivre');
});

test('keeps legacy behaviour for empty or unknown URLs', () => {
  assert.equal(marketplaceFromUrl(undefined), 'amazon');
  assert.equal(marketplaceFromUrl('not a url'), 'amazon');
  assert.equal(marketplaceFromUrl('https://evilmercadolivre.com.br/x'), 'amazon');
  assert.equal(marketplaceFromUrl('https://mercadolivre.com.br.evil.test/x'), 'amazon');
});

test('buy label names the right store for each link type', () => {
  assert.equal(buyLabel('amazon', 'product'), '🛒 Ver preço na Amazon');
  assert.equal(buyLabel('amazon', 'search'), '🔎 Ver opções na Amazon');
  assert.equal(buyLabel('amazon', 'offer'), '🏷️ Conferir oferta na Amazon');
  assert.equal(buyLabel('mercadolivre', 'product'), '🛒 Ver preço no Mercado Livre');
  assert.equal(buyLabel('mercadolivre', null), '🛒 Ver preço no Mercado Livre');
});

test('disclosure matches the affiliate program of the marketplace', () => {
  assert.match(affiliateDisclosure('amazon'), /Programa de Associados da Amazon/);
  assert.match(affiliateDisclosure('mercadolivre'), /Programa de Afiliados do Mercado Livre/);
  assert.doesNotMatch(affiliateDisclosure('mercadolivre'), /Amazon/);
});
