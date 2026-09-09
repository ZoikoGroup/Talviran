# frontend

The web client — a chat-style research interface for Talvrin.

It consumes the backend REST/JSON API (`API-001`) — it holds **no** business logic,
never talks to data vendors or model providers directly, and treats server-side
policy/rights decisions as authoritative.

## Status

**UI prototype.** The chat interface is built; **no backend is connected yet.**
Replies come from a local placeholder in [`src/mockReply.js`](src/mockReply.js),
which will be replaced by a call to `POST /api/v1/research` once the API exists.

## Stack

React 18 + Vite 6 (plain JS, no TypeScript yet).

## Running it

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
```

Other scripts: `npm run build`, `npm run preview`.

## Structure

```
src/
├── main.jsx              app entry
├── App.jsx               layout + chat state
├── index.css             theme (CSS variables) + all styles
├── mockReply.js          placeholder reply logic — replace with API call
└── components/
    ├── Sidebar.jsx       brand, new thread, recent threads, account
    ├── Message.jsx       one message + its evidence citations
    ├── EmptyState.jsx    welcome screen + suggested prompts
    └── Composer.jsx      auto-growing input, Enter to send
```

## What's implemented

- Chat thread with user / assistant messages and a typing indicator
- Multiple research threads, auto-titled from the first message
- Collapsible sidebar
- Empty state with suggested prompts
- Auto-growing composer (Enter sends, Shift+Enter newlines)
- **Evidence citation blocks** under assistant replies — the placeholder for the
  real source-linked evidence contract (`EVID-001`)
- **Recommendation-safe guardrail demo** — asking "should I buy this?" is
  redirected to factual workflows instead of answered, per `PRD-001 §11` /
  `POL-001`

## Not yet built

Search, instrument evidence workspace, calculators, comparison, watchlists,
monitoring rule creation and alert history (see `PRD-001` §7). Auth, real
API wiring, freshness/degradation states, i18n and accessibility audit.
