FROM node:22-alpine AS build
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
ARG VITE_PLAYBACK_API_BASE_URL=http://localhost:8001
ARG VITE_SIMENV_API_BASE_URL=http://localhost:8000
ENV VITE_PLAYBACK_API_BASE_URL=$VITE_PLAYBACK_API_BASE_URL \
    VITE_SIMENV_API_BASE_URL=$VITE_SIMENV_API_BASE_URL
RUN npm run build

FROM nginx:alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/
