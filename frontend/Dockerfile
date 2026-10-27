FROM node:22-alpine AS build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_POSTHOG_KEY
ARG VITE_POSTHOG_HOST=https://us.i.posthog.com
ARG VITE_POSTHOG_TEST_PROJECT=false
ENV VITE_POSTHOG_KEY=$VITE_POSTHOG_KEY VITE_POSTHOG_HOST=$VITE_POSTHOG_HOST VITE_POSTHOG_TEST_PROJECT=$VITE_POSTHOG_TEST_PROJECT
RUN npm run build
FROM nginx:alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
EXPOSE 80
