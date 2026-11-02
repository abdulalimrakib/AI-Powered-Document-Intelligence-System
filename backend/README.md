# AI-Powered Document Intelligence System — Backend

Express API for the AI-Powered Document Intelligence System.

## Run locally

```bash
npm install
cp .env.example .env
npm run dev
```

The server runs at http://localhost:3002. Check it with http://localhost:3002/health.

| Script | What it does |
|---|---|
| `npm run dev` | Start with auto-reload (nodemon) |
| `npm start` | Start once |
| `npm run typecheck` | TypeScript check |

## Project structure

```
app.ts                      Express app: CORS, routes, error handling
server.ts                   Starts the server on PORT
config/env.config.ts        Settings from .env.local / .env
middleware/error.handler.ts JSON 404 and error responses
```
