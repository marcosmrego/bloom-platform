import { defineConfig } from 'astro/config';
import node from '@astrojs/node';

export default defineConfig({
  output: 'server',
  adapter: node({
    mode: 'standalone',
  }),
  server: {
    port: parseInt(process.env.PORT || '3000'),
    host: '0.0.0.0',
  },
  vite: {
    define: {
      'process.env.BLOOM_API': 'process.env.BLOOM_API',
    },
    server: {
      allowedHosts: ['bloom.expansao-ai.com.br', '.expansao-ai.com.br'],
    },
  },
});
