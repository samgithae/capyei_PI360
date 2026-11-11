# Frontend UI standard (Metronic 9)

Metronic 9.5 (layout-1, Tailwind 4, Radix-based `components/ui/*`) is the only design system.
Do not add another template or UI kit. Check in this order before building anything:

1. A shared component in `src/components/shared/` or `src/components/data-card.tsx`.
2. A Metronic primitive in `src/components/ui/` (card, table, dialog, alert-dialog, select, badge, tabs, sheet, data-grid...).
3. Only then a new component. If it recurs, add it to `components/shared/` and list it below.

## Shared components

| Component | Use it for |
|---|---|
| `PageHeader` | Every page top: breadcrumbs, title, status badges, meta line, action buttons |
| `Section` | A titled card (optional header action; `flush` for tables) |
| `DetailList` | Label/value attributes of a record (empty shows a dash) |
| `SummaryStatCard` | A headline count. Real API numbers only, never hard-coded |
| `StatusBadge` | Any status. One colour map; add new statuses there |
| `FormModal` | Add/edit forms: labels, `*` on required, error line, Cancel/Save |
| `ConfirmDialog` | Before any delete or hard-to-undo change |
| `ActivityTimeline` | Audit history (`/history` endpoints) |
| `DataCard`, `SearchBox`, `FilterSelect`, `Pager` | List pages (`components/data-card.tsx`) |
| `EmptyState`, `ErrorState`, `LoadingState`, `Notice` | Every data region (`components/states.tsx`) |

## Page layout

Breadcrumbs, title, actions (`PageHeader`) -> summary cards -> main content in cards ->
activity/history. Detail pages use a 2/3 + 1/3 grid: information on the left, activity on the right.

## Rules

- Use real backend data only. If an endpoint does not exist, leave the section out.
- Status colour is always paired with the status text.
- Feedback: `toast.success` / `toast.error` (sonner) for results; inline error inside a modal.
- Show an action only if `can('<permission>')`; the API remains the authority.
- Forms in a `FormModal`; native `<select>` is not used, use the Metronic `Select`.
- Every list and panel handles loading, empty and error states.
- Run before committing: `npx prettier --write src`, `npm run typecheck`, `npm run lint`.

## Known gaps

`import-new-page`, `users-page` and `employer-form` still use a native `<select>`;
`duplicates-page` has a hand-picked badge; `profile-page`, `directory-page` and import pages
use `Toolbar` rather than `PageHeader`. Migrate them when each page is next touched.
