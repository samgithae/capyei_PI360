# PI 360 frontend

React 19 + TypeScript + Vite, built on the Metronic 9.5.0 React starter kit
(licensed by the implementer; CAP-YEI accepted it under D-060).

- `src/components/ui` — Metronic/shadcn components, unchanged from the kit.
- `src/components/layouts/layout-1` — the app shell. The Vite kit ships without
  its layout files (I-05), so this was ported from the kit's Next.js edition:
  `next/link` and `next/navigation` swapped for React Router; the search,
  notification, chat, apps and mega-menu widgets dropped (not shipped and not in
  our design).
- `src/config/layout-1.config.tsx` — draft sidebar from planning doc 20 §3.
- `src/lib/api.ts` — API client: session cookie, CSRF header, no stored tokens.

Kit changes outside the layout: demo layouts, pages and media removed;
`create-demo-user`/`debug-auth` scripts removed; the `ajv` override removed
(it broke ESLint); `npm audit fix` applied.

```bash
npm ci
npm run dev        # http://localhost:5173, proxies /api to localhost:8000
npm run lint
npm run build
```
