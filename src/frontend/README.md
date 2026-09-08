# Hermes frontend

Next.js App Router UI for Hermes by TheKade. It streams answers from the
backend over Server-Sent Events and renders sources, trust badges, figures and
the agent's reasoning trace.

## Structure

| Path | Contents |
|---|---|
| `app/` | Routes. `/` redirects to `/chat`, which creates a session and replaces the URL with `/chat/[sessionId]` |
| `components/` | `hermes-app` owns session state and the SSE connection; panel, sidebar, answer card, document modal and image lightbox render it |
| `lib/` | `api.ts` API and SSE client, `constants.ts` app config and suggested queries, `validation/` Zod schemas |
| `types/hermes.ts` | Response types shared with the backend contract |

## Running

```bash
npm install
npm run dev      # http://localhost:3000
npm run build
npm run lint
```

Set `NEXT_PUBLIC_API_URL` if the backend is not on `http://localhost:8000`:

```bash
cp .env.local.example .env.local
```

It is a `NEXT_PUBLIC_` variable, so it is inlined at build time.
