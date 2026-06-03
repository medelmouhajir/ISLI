FROM node:20-alpine

RUN apk add --no-cache curl

WORKDIR /app

COPY package*.json ./
RUN npm install --production

COPY index.js ./

# Create auth directory
RUN mkdir -p /auth/whatsapp && chown -R node:node /auth/whatsapp

USER node

ENV PORT=3001
ENV AUTH_BASE_DIR=/auth/whatsapp
ENV LOG_LEVEL=info

EXPOSE 3001

CMD ["node", "index.js"]
