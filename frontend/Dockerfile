FROM node:22-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
ENV BLOOM_API=http://bloom-api:8000
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./
ENV HOST=0.0.0.0
ENV PORT=3000
ENV BLOOM_API=http://bloom-api:8000
EXPOSE 3000
CMD ["node", "dist/server/entry.mjs"]
