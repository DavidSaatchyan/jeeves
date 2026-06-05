# Integrations Hub — Design Audit & Modernization Proposal

## 1. Current State

### Layout
- 3 section stacks (CRM / Channels / Widget) with uppercase 14px titles
- Responsive grid: `auto-fill, minmax(320px, 1fr)` — collapses to 1 column on narrow
- Skeleton loading before API fetch, hidden after render

### Cards
- `.hub-card`: 20px padding, 44px icon, name + status badge + action button
- Icon box: 44x44px, `border-radius: 10px`, `flex-shrink: 0`
- Background: `--surface` (`#1a1a1e`), border: `--border` (`rgba(255,255,255,0.11)`)
- Hover: brighten border to `--border-bright`, slight bg lighten
- Status pill: green/red/muted with matching tinted background

### Problems
- Cards feel **flat** — no depth, no shadow, no visual hierarchy
- Icon area is **small** (44px) — brand logos get lost
- Connected/disconnected difference is minimal — just a tiny pill badge
- No **search or filter** — 3 sections, but growing beyond that
- **No entrance animation** — cards just pop in
- **No empty state** guidance — skeleton → blank if error
- **All cards same size/shape** — no distinction between "configured with data" vs "just connected"

---

## 2. Design Goals (Brand-Aligned)

| Goal | Rationale |
|------|-----------|
| Feel premium but not noisy | Our brand is dark, clean, professional — no gradients-for-decoration |
| Status scannable in 300ms | Green dot + label = instantly readable, no pill scanning |
| Cards invite interaction | Hover lift + subtle glow makes cursor naturally click |
| Respect existing tokens | Use `--accent`, `--surface`, `--green`, `--red`, `--amber`, `--muted2` — no new colors |
| Lightweight animations | `transition: all .2s cubic-bezier(.22,1,.36,1)` — fast, no framer-motion dep |
| Searchable by Q2 2026 | Structure markup for future filter without layout changes |

---

## 3. Recommendations

### 3.1 Card Visual Hierarchy (Highest Impact)

**Current:**
```
┌──────────────────────────────────┐
│ [icon]  Name            [pill]   │
│         status                   │
│         [Connect/Disconnect]     │
└──────────────────────────────────┘
```

**Proposed:**
```
┌──────────────────────────────────┐
│ ● Connected  │    [icon xl]       │
│              │                    │
│   Name (18px, 700)               │
│   Description or last-sync meta   │
│                                   │
│        [Configure]  [Disconnect]  │
└──────────────────────────────────┘
```

Key changes:
- **Icon** grows to 48-52px, moves to right side or centered top (depending on card orientation)
- **Status** moves to top-left as `● Connected` dot + label (green/gray/red)
- **Name** larger (15→17px), **description** always shown (truncate to 2 lines)
- **Actions** at bottom, revealed entirely (no hover-reveal — keeps accessibility)
- **Connected cards** get a subtle **left accent border** (3px `--green` or `--accent`)

### 3.2 Card Depth & Hover

**Default state:**
```css
.hub-card {
  background: var(--surface);
  border: 1px solid var(--border);
  box-shadow: 0 1px 2px rgba(0,0,0,0.2);
  transition: all .2s cubic-bezier(.22,1,.36,1);
}
```

**Hover state:**
```css
.hub-card:hover {
  border-color: var(--border-bright);
  box-shadow: 0 4px 16px rgba(0,0,0,0.3);
  transform: translateY(-2px);
}
```

This single change — adding shadow + lift — makes the page feel 2× more premium. No extra color, no gradient, pure depth.

### 3.3 Connected State — Accent Border

When `i.status === 'connected'`:
```css
.hub-card.connected {
  border-left: 3px solid var(--green);
  border-image: none;
}
```

For channels (Instagram/WhatsApp) that don't have a CRM-style connection:
```css
.hub-card.active {
  border-left: 3px solid var(--accent);
}
```

This gives **immediate visual weight** to active integrations without adding UI noise.

### 3.4 Status Badge → Inline Dot

Replace pill badges with a compact dot + text:

```css
.status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
.status-dot.ok { background: var(--green); box-shadow: 0 0 6px rgba(52,211,153,0.4); }
.status-dot.err { background: var(--red); box-shadow: 0 0 6px rgba(229,72,77,0.4); }
.status-dot.muted { background: var(--muted2); }
```

Rendered as:
```html
<span><span class="status-dot ok"></span> Connected</span>
```

The glow (`box-shadow`) adds the "premium" feel while staying minimal.

### 3.5 Section Headers with Subtle Dividers

Current:
```html
<div class="hub-section-title">CRM</div>
```

Proposed:
```html
<div class="hub-section">
  <div class="hub-section-header">
    <div class="hub-section-title">CRM</div>
    <div class="hub-section-count">2 integrations</div>
  </div>
  <div class="hub-section-divider"></div>
  <div class="hub-grid">...</div>
</div>
```

CSS:
```css
.hub-section-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 8px; }
.hub-section-count { font-size: 12px; color: var(--muted2); }
.hub-section-divider { height: 1px; background: var(--border); margin-bottom: 16px; }
```

The divider grounds the section visually.

### 3.6 Card Entrance Animation

Cards animate in staggered:

```css
.hub-card { opacity: 0; transform: translateY(12px); transition: opacity .35s ease, transform .35s ease, border-color .2s ease, box-shadow .2s ease; }
.hub-card.visible { opacity: 1; transform: translateY(0); }
```

JS:
```js
function renderGrid(gridId, items, renderFn) {
  const grid = document.getElementById(gridId);
  grid.innerHTML = items.map((item, i) => renderFn(item, i)).join('');
  requestAnimationFrame(() => {
    grid.querySelectorAll('.hub-card').forEach((el, i) => {
      setTimeout(() => el.classList.add('visible'), i * 60);
    });
  });
}
```

No dependency needed — 3 lines of JS, one CSS rule.

### 3.7 Loading State — Shimmer Card

Replace skeleton `<div>`s with animated shimmer cards matching the new card shape:

```css
.skel-card { border-radius: var(--radius); overflow: hidden; background: var(--surface); border: 1px solid var(--border); }
.skel-shimmer { height: 100%; background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.04) 50%, transparent 100%); background-size: 200% 100%; animation: shimmer 1.8s ease infinite; }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
```

The skeleton HTML becomes a single div with `.skel-card` and one `.skel-shimmer` child.

### 3.8 Empty State

When a section has zero integrations:

```html
<div class="empty-state">
  <div class="empty-state-icon">
    <svg viewBox="0 0 40 40" fill="none" stroke="var(--muted2)" stroke-width="1.5">
      <rect x="4" y="4" width="32" height="32" rx="6"/>
      <path d="M12 20h16M20 12v16"/>
    </svg>
  </div>
  <div class="empty-state-title">No integrations yet</div>
  <div class="empty-state-desc">Connect your first CRM or channel to get started.</div>
</div>
```

CSS:
```css
.empty-state { padding: 40px 20px; text-align: center; }
.empty-state-icon { margin-bottom: 12px; opacity: 0.5; }
.empty-state-title { font-size: 15px; font-weight: 600; color: var(--muted); margin-bottom: 4px; }
.empty-state-desc { font-size: 13px; color: var(--muted2); }
```

### 3.9 Action Buttons Consistency

Current:
- Connected: `Disconnect` button (ghost sm danger) in card + card is clickable
- Disconnected: `Connect` button (btn sm) in card + card is clickable
- Widget: `Configure` button

Proposed — keep buttons clean, no modal-trigger confusion:
- Non-connected cards: **primary "Connect" button** accent-colored
- Connected cards: **secondary "Manage" button** (ghost) + separate **"Disconnect"** (ghost danger)
- Card itself no longer clickable (button is the action affordance)

But the user wants to keep the card clickable + button. So keep both, just refine visual.

### 3.10 Responsive Refinements

At `minmax(320px, 1fr)`, on a 1200px screen we get 3 columns. On 900px: 2. On 640px: 1. That's fine, but add:

```css
@media (max-width: 500px) {
  .hub-card { padding: 16px; gap: 12px; }
  .hub-card-icon { width: 36px; height: 36px; }
  .hub-card-icon svg, .hub-card-icon img { width: 18px; height: 18px; }
  .hub-card-name { font-size: 14px; }
}
```

Prevents cramped feel on phones.

---

## 4. Implementation Plan

### Phase 1 — Card Visuals (highest impact, fewest lines)
1. Add `box-shadow` + `transform: translateY(-2px)` to hover
2. Add `.connected`/`.active` left accent border
3. Replace pill badges with `.status-dot` + text
4. Enlarge icon area to 48px

### Phase 2 — Layout Polish
1. Section headers with divider line
2. Integration count per section
3. Mobile responsive padding

### Phase 3 — Animation & Micro-interactions
1. Card entrance stagger
2. Shimmer loading animation
3. Status dot glow animation

### Phase 4 — Empty States
1. Per-section empty state with icon + guidance
2. Error state recovery

---

## 5. Visual Mock (text-based)

```
┌─ CRM ───────────────────────── 2 integrations ─┐
│ ─────────────────────────────────────────────── │
│ ┌────────────────────┐  ┌────────────────────┐  │
│ │ ● Connected        │  │ ○ Not configured   │  │
│ │                    │  │                    │  │
│ │ [cliniko logo]     │  │ [pabau icon]       │  │
│ │                    │  │                    │  │
│ │ Cliniko            │  │ Pabau              │  │
│ │ Patients & apps    │  │ Practice management│  │
│ │ synced 2m ago      │  │                    │  │
│ │                    │  │                    │  │
│ │ [Manage] [Danger]  │  │    [Connect]       │  │
│ └────────────────────┘  └────────────────────┘  │
│                                                    │
│ ┌─ Channels ──────────────── 2 integrations ──┐   │
│ │ ──────────────────────────────────────────── │   │
│ │ ┌────────────────────┐  ┌────────────────────┐  │
│ │ │ ● Active           │  │ ○ Not configured   │  │
│ │ │ [whatsapp]         │  │ [instagram]        │  │
│ │ │ WhatsApp           │  │ Instagram          │  │
│ │ │ Business API       │  │ Business account   │  │
│ │ │ [Configure] [Disc] │  │    [Connect]       │  │
│ │ └────────────────────┘  └────────────────────┘  │
└────────────────────────────────────────────────────┘
```

---

## 6. Why These Changes Work Within Brand

| Change | Brand Alignment |
|--------|-----------------|
| Shadow + lift | Uses existing `--surface`/`--border`, adds depth without color |
| Left accent border | `--green`/`--accent` already exist — no new tokens |
| Status dot | Pill colors are `--green`/`--red` — same colors, smaller footprint |
| Section divider | Uses `--border` — already in system |
| Entrance stagger | `opacity` + `translateY` — no JS library, pure CSS transition |
| Shimmer loading | Uses existing `@keyframes shimmer` pattern from base.html |
| Empty state icon | SVG inline with `--muted2` stroke — matches existing `--muted2` text |
| Responsive padding | Uses existing `--radius`, `--surface` — inherits everything |
