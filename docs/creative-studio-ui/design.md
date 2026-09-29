# Creative Studio — design intent

## Product-specific direction
Agentic Marketing is a daily workspace for a Vietnamese marketing team. The main visual artifact is a draft post in progress, so the UI should feel like a writing studio: open white workspace, restrained black type, and a deliberate deep-pink action color. Lists remain scannable rows; only active work receives a bounded panel.

## Tokens
- Canvas: `#FFFFFF`; secondary surface: `#F4F5F7`.
- Ink: `#000000`; muted text: `#5B5D67`; divider: `#D9DBE1`.
- Primary: `#B8125C`; semantic success/warning/error colors retain their meanings.
- Be Vietnam Pro, locally served, with a system sans-serif fallback and included OFL license.
- Body 15–16px / 1.6; section titles 20–24px; page titles 28–36px.
- Workspace rail 224px; editor inspector 360–400px; content width capped at 1440px; reading copy capped near 72 characters.
- Controls 6–8px radius; work panels 12px; post preview 16px. Motion is action-led, 120–220ms, and removed when reduced motion is preferred.

## Layout concept
Desktop pages use a light 224px navigation rail beside a wide left-aligned work surface. The post editor gets the distinctive treatment: an uninterrupted writing canvas on the left, a narrow inspector on the right, and the exact saved-version status visible at the point of work. Mobile keeps the writing surface first and turns the inspector into URL-addressable tabs below it.

```text
┌────────────┬──────────────────────────────────────────────────┐
│ workspace  │ Breadcrumb                         account state │
│ overview   ├─────────────────────────────────┬────────────────┤
│ brand      │ Page title and primary action   │                │
│ documents  │                                 │ Inspector      │
│ campaigns  │ Writing surface / list rows     │ Preview /      │
│ publishing │                                 │ sources /      │
│ market     │                                 │ review         │
│ analytics  └─────────────────────────────────┴────────────────┘
└────────────┴──────────────────────────────────────────────────┘
```

## Deliberate restraint
The only strong decorative note is the deep-pink action/selection color. No dashboard hero, gradient, repeated card grid, all-caps eyebrow, generic entrance animation, stock imagery, or invented metrics. Status colors remain semantic; previews show only real user content.

## First-pass critique before implementation
The old palette's dark forest sidebar and green action colors compete with the writing surface and make every section feel like the same card. The repeated eyebrow and global page-arrive animation add decoration without helping a marketing task. The chosen redesign moves navigation onto the light canvas, reserves panel boundaries for active work, and removes route-level entrance motion. This is specific to an editing and review workflow rather than a generic analytics dashboard.

## Visual review

After the first screenshots, the overview still displayed a row of four KPI-like cards in fixture mode while the real route had a different structure. The overview was consolidated into one API-backed “Việc nên làm tiếp” workspace view with a short list of brand, document and campaign states. This keeps fixture and real-mode hierarchy aligned and removes summary counts that did not help choose the next task.

The mobile document table intentionally remains a horizontally scrollable table so all its columns and row actions stay available. QA showed that the crop did not explain itself, so the region is now keyboard-focusable and a short mobile-only scroll hint is visible. The editor inspector stays below the writing area on narrow screens, so the caption remains the first task.

The final screenshots and check results are in [`verification.md`](verification.md) and `screenshots/`. Fixture screenshots retain a visible “Bản demo” label; the login capture is refreshed from the real preview without entering credentials.
