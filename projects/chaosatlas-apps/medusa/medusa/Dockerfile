FROM node:20-bookworm-slim

WORKDIR /app
COPY package*.json ./
COPY apps/backend/package*.json apps/backend/
RUN npm ci

COPY . .
RUN npm run build --workspace=@dtc/backend

EXPOSE 9000
CMD ["npm", "run", "start", "--workspace=@dtc/backend"]
