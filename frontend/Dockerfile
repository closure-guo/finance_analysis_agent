# ── 前端镜像：多阶段构建（node 编译 → nginx 托管）──────────────────

# 阶段 1：构建
FROM node:20-alpine AS build
WORKDIR /app
# 使用国内 npm 镜像加速
RUN npm config set registry https://registry.npmmirror.com --strict-ssl=false
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# 阶段 2：运行（nginx 托管静态资源 + 反代 /api 到后端）
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
