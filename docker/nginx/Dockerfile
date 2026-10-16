FROM node:20-alpine AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./

# npm 源：默认官方 registry。国内服务器无法直连 registry.npmjs.org 时，
# 构建时传 --build-arg NPM_REGISTRY=https://registry.npmmirror.com 即可。
ARG NPM_REGISTRY=https://registry.npmjs.org
RUN npm config set registry "${NPM_REGISTRY}" \
    && npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine

COPY docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY docker/nginx/conf.d /etc/nginx/conf.d
COPY --from=frontend-builder /frontend/dist /usr/share/nginx/html
