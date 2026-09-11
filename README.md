# Bird Photos

A personal web app for browsing and organizing bird photos, with AI-assisted species
identification and automatic burst/duplicate detection.

## Structure

- `web/` — Next.js (TypeScript) frontend, deployed to Vercel: https://web-gamma-black-17.vercel.app
- `worker/` — Python (FastAPI) backend: Google Photos import, image scoring, burst
  grouping, AI species classification, deployed to Fly.io: https://birdphotos-worker.fly.dev

See `.claude` plan history for the full architecture and implementation plan.

## Development

```sh
# Frontend
cd web && npm run dev

# Backend
cd worker && uvicorn app.main:app --reload
```

## Deployment

- `web/` auto-deploys to Vercel on every push to `main`.
- `worker/` deploys manually: `cd worker && fly deploy`.
