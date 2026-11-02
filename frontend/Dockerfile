FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.29-alpine
# Rendered to /etc/nginx/conf.d/default.conf by the image's envsubst entrypoint.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
ENV PROXY_READ_TIMEOUT=300 \
    PROXY_SEND_TIMEOUT=300 \
    NGINX_ENVSUBST_FILTER=^PROXY_
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
