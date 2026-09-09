# frontend

The web client — a chat-style research interface for Talvrin.

It consumes the backend REST/JSON API (`API-001`) — it holds **no** business logic,
never talks to data vendors or model providers directly, and treats server-side
policy/rights decisions as authoritative.

## Status

**UI prototype.** The chat interface is built; **no backend is connected yet.**
Replies come from a local placeholder in [`src/data/mockReply.ts`](src/data/mockReply.ts),
which will be replaced by a call to `POST /api/v1/research` once the API exists.

## Stack

- **React 18** + **Vite 6**
- **TypeScript** (strict)
- **Tailwind CSS 3** with CSS-variable design tokens
- **shadcn/ui** structure (`components.json`, `@/components/ui`, `@/lib/utils`)
- **lucide-react** icons

## Running it

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

Other scripts: `npm run build` (typechecks then builds), `npm run typecheck`,
`npm run preview`.

## Adding shadcn components

The project is configured for the shadcn CLI, so new primitives drop straight in:

```bash
npx shadcn@latest add dialog dropdown-menu tooltip
```

They land in `src/components/ui/`. **Keep that path** — the `@/components/ui`
alias in `components.json` and `tsconfig.json` is what lets the CLI and every
generated component resolve `cn()` and sibling primitives without hand-editing
imports.

## Structure

```
src/
├── main.tsx                    app entry
├── App.tsx                     layout, thread state, theme
├── index.css                   Tailwind layers + design tokens + moon glow
├── lib/
│   └── utils.ts                cn() helper
├── data/
│   └── mockReply.ts            placeholder replies — replace with API call
└── components/
    ├── Sidebar.tsx             brand, threads, theme toggle, account
    ├── Message.tsx             message + fact table + evidence card
    ├── Composer.tsx            compact composer for active threads
    └── ui/                     shadcn primitives
        ├── button.tsx
        ├── textarea.tsx
        └── talvrin-moon-chat.tsx   hero / landing composer
```

## Design tokens

Theme is driven by CSS variables in `src/index.css`; the `.light` class on
`<html>` overrides them. Alongside the standard shadcn tokens there are three
Talvrin-specific semantic colours used by evidence pills:

| Token | Meaning |
|---|---|
| `fresh` | data within its freshness SLO (`CURRENT`) |
| `delayed` | delayed but within tolerance (`DELAYED`) |
| `stale` | beyond tolerance (`STALE`) |

These map to the canonical freshness vocabulary in `PRD-001` Appendix A.

The aurora arc behind the hero (`.moon-glow`) is pure CSS — no remote image — so
it works offline and follows the active theme.

## What's implemented

- Full-screen hero landing state with aurora glow, auto-resizing composer and
  eight quick-action prompts
- Chat thread with user bubbles, assistant turns and a typing indicator
- Multiple research threads, auto-titled from the first message
- Collapsible sidebar, light/dark toggle persisted to `localStorage`
- **Evidence cards** — collapsible, per-source icons, as-of metadata and
  freshness pills (the placeholder for `EVID-001`)
- **Fact tables** — typed instrument terms with monospaced values
- **Recommendation-safe guardrail demo** — asking "should I buy this?" is
  redirected to factual workflows instead of answered, per `PRD-001 §11` /
  `POL-001`

## Not yet built

Search, instrument evidence workspace, calculators, comparison, watchlists,
monitoring rule creation and alert history (see `PRD-001` §7). Auth, real API
wiring, freshness/degradation states end-to-end, i18n and an accessibility audit.
