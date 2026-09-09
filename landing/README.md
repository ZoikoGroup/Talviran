# landing

The public marketing site for Talvrin — the pre-login surface people see
before they reach the research app in [`frontend/`](../frontend).

Kept separate from the app because it has different concerns: it is public,
SEO-indexed, largely static, and can ship on its own release cadence without
touching the authenticated product.

## Planned content

- Hero and product positioning
- What Talvrin does: source-linked facts, reproducible calculations,
  objective monitoring
- The trust story — evidence, provenance and reproducibility
- Pricing / plan tiers (Free · Core · Research · Pro, per `PRD-001` §12)
- Legal and jurisdiction-appropriate disclosures

## Constraints

Marketing copy is **not** free-form. Per `POL-001`, customer-facing copy is a
versioned, approved artefact, and per `PRD-001` §11 the same
recommendation-safe perimeter applies here as in the app: no buy/sell/hold
language, no performance claims, no implied advice. Copy shown in an activated
jurisdiction must come from that jurisdiction's approved copy bundle.

## Status

Placeholder — not yet built. Stack to be decided.
