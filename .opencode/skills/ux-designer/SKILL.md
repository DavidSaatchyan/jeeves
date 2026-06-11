---
name: ux-designer
description: "Professional UI/UX design intelligence for web and mobile applications. Includes 49 UI styles, 43 industry-specific color palettes, 45 font pairings, 51 product types, 80+ UX guidelines, 20 chart types, and 10 technology stacks. Domains: style, color, typography, product, ux, chart, landing. Supports React, Next.js, Vue, Angular, Svelte, SwiftUI, React Native, Flutter, HTML+Tailwind, and shadcn/ui. Actions: plan, build, create, design, implement, review, fix, improve, optimize, check. Projects: website, landing page, dashboard, admin panel, e-commerce, SaaS, portfolio, blog, mobile app. Integrates with openflo-mcp search engine for data-driven design system generation."
license: MIT
compatibility: opencode
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: design
  triggers: UI, UX, design, wireframe, mockup, user flow, accessibility, usability, design system, style, color, typography, font, layout, responsive, mobile, dashboard, landing page
  role: specialist
  scope: design
  output-format: document + code
  related-skills: frontend-developer, backend-developer, test-master, security-engineer
  data-files: styles.json, colors.json, fonts.json, products.json, ux-rules.json, charts.json
  search-engine: node .opencode/skills/shared/search.js
---

# UX Designer Pro Max — Design Intelligence

Comprehensive UI/UX design guide for web and mobile applications. Contains 49 UI styles, 43 industry-specific color palettes, 45 font pairings, 51 product types with reasoning rules, 80+ UX guidelines, and 20 chart types. Data-driven design system generation with priority-based recommendations.

## When to Apply

Use this skill when the task involves **UI structure, visual design decisions, interaction patterns, or user experience quality control**.

### Must Use

This skill must be invoked in the following situations:

- Designing new pages (landing page, dashboard, admin panel, SaaS, mobile app)
- Creating or refactoring UI components (buttons, modals, forms, tables, charts)
- Choosing color schemes, typography systems, spacing standards, or layout systems
- Reviewing UI code for user experience, accessibility, or visual consistency
- Implementing navigation structures, animations, or responsive behavior
- Making product-level design decisions (style, information hierarchy, brand expression)
- Improving perceived quality, clarity, or usability of interfaces

### Recommended

This skill is recommended in the following situations:

- UI looks "not professional enough" but the reason is unclear
- Receiving feedback on usability or experience
- Pre-launch UI quality optimization
- Aligning cross-platform design (Web / iOS / Android)
- Building design systems or reusable component libraries

### Skip

This skill is not needed in the following situations:

- Pure backend logic development
- Only involving API or database design
- Performance optimization unrelated to the interface
- Infrastructure or DevOps work
- Non-visual scripts or automation tasks

**Decision criteria**: If the task will change how a feature looks, feels, moves, or is interacted with, use this skill.

## Rule Categories by Priority

*Use priority 1→10 to decide which category to focus on. Search data files for detailed recommendations when needed.*

| Priority | Category | Impact | Data Domain | Key Checks | Anti-Patterns |
|----------|----------|--------|-------------|------------|---------------|
| 1 | Accessibility | CRITICAL | `ux` | Contrast 4.5:1, Alt text, Keyboard nav, ARIA labels | Removing focus rings, Icon-only buttons, Color-only indicators |
| 2 | Touch & Interaction | CRITICAL | `ux` | Min 44×44pt targets, 8px+ spacing, Loading feedback | Hover-only interactions, Instant state changes, Small targets |
| 3 | Performance | HIGH | `ux` | WebP/AVIF, Lazy loading, CLS < 0.1, Virtual lists | Layout thrashing, Unoptimized images, No loading states |
| 4 | Style Selection | HIGH | `style`, `product` | Match product type, Design tokens, SVG icons | Mixed styles, Emoji icons, Inconsistent elevation |
| 5 | Layout & Responsive | HIGH | `ux` | Mobile-first, Safe areas, Readable 16px, No h-scroll | Fixed px containers, Disable zoom, Nested scrolls |
| 6 | Typography & Color | MEDIUM | `typography`, `color` | Font pairing, Semantic tokens, Line-height 1.5 | Raw hex values, Low contrast, No dark mode |
| 7 | Animation | MEDIUM | `ux` | 150-300ms duration, Transform/opacity, Reduced motion | Animate layout props, Decorative-only, No easing |
| 8 | Forms & Feedback | MEDIUM | `ux` | Visible labels, Inline errors, Submit feedback | Placeholder-only label, Errors at top only, No recovery |
| 9 | Navigation Patterns | HIGH | `ux` | Predictable back, Max 5 tabs, Deep linking | Broken back, Overloaded nav, No deep links |
| 10 | Charts & Data | LOW | `chart` | Right chart type, Legends, Accessible colors | Color-only meaning, Pie >5 categories, No data table |

## How to Use the Search Engine

This skill includes a data-driven search engine. Use it for design system generation and domain-specific lookups.

```bash
# Generate complete design system
node .opencode/skills/shared/search.js "beauty spa wellness" --design-system -p "Serenity Spa"

# Search specific domain
node .opencode/skills/shared/search.js "minimal dark mode" --domain style

# Color palette search
node .opencode/skills/shared/search.js "fintech banking" --domain color

# Font pairing search
node .opencode/skills/shared/search.js "elegant modern" --domain fonts

# UX guidelines search
node .opencode/skills/shared/search.js "form validation" --domain ux-rules

# Product type lookup
node .opencode/skills/shared/search.js "crypto exchange" --domain products

# Chart recommendations
node .opencode/skills/shared/search.js "real-time dashboard" --domain charts

# JSON output for programmatic use
node .opencode/skills/shared/search.js "fintech" --design-system --format json
```

### Available Domains

| Domain | Data | Use For |
|--------|------|---------|
| `styles` | 49 styles | UI style selection, effects, anti-patterns |
| `colors` | 43 palettes | Industry-specific color schemes |
| `fonts` | 45 pairings | Font pairing with mood and Google Fonts imports |
| `products` | 51 types | Product type → style/color/pattern matching |
| `ux-rules` | 80+ rules | UX guidelines with priority levels |
| `charts` | 20 types | Chart selection and accessibility |

### Available Stacks

| Stack | Focus |
|-------|-------|
| Website / Landing Page | Hero sections, CTA strategy, trust signals |
| Web App (React/Next.js/Vue) | Component architecture, state management |
| Mobile (iOS/Android) | Platform HIG, navigation, gestures |
| Dashboard / Analytics | Data density, chart selection, filters |
| e-Commerce | Product display, cart flow, conversion |

## Quick Reference — 10 Priority Categories

### 1. Accessibility (CRITICAL)

Every UI must be usable by people with disabilities. This is not optional.

| Rule | Do | Don't |
|------|----|-------|
| **Color Contrast** | Maintain 4.5:1 for normal text, 3:1 for large text (18px+ bold / 24px+ regular). Test all pairs. | Use low-contrast text. Use gray-on-gray. Rely on color alone. |
| **Focus States** | Visible focus ring (2-4px, 2px offset) on all interactive elements. Focus order = visual order. | outline: none without custom focus. Hide focus from keyboard users. |
| **Alt Text** | Descriptive alt for meaningful images. `alt=""` for decorative. aria-label for icon buttons. | Filenames as alt text ("image001.jpg"). Empty alt on info images. |
| **Keyboard Navigation** | All functionality via keyboard (Tab, Enter, Escape, Arrows). No tab traps. | tabindex > 0. Mouse-only interactions. Trapped focus in modals. |
| **Form Labels** | Visible label per field with for/htmlFor attribute. Describes purpose. | Placeholder as only label. Hidden labels. Generic labels ("Field 1"). |
| **Heading Hierarchy** | Sequential h1→h2→h3. One h1 per page. Headings describe following content. | Skipping levels (h1→h3). Headings for styling only. Multiple h1s. |
| **Reduced Motion** | Respect `prefers-reduced-motion`. Reduce/disable animations, parallax. | Ignore user motion preferences. Non-stop animations without alternatives. |
| **Screen Reader** | Semantic HTML, ARIA landmarks, proper roles. Test with VoiceOver/NVDA. | Divs for interactive elements. No aria-live for dynamic updates. |
| **Skip Navigation** | "Skip to main content" as first focusable element. | Skip link only for keyboard users — make it visible on focus. |
| **Text Scaling** | Support system font scaling. Use rem/em. Test at largest setting. | Lock font sizes with px. Clip/truncate text at large sizes. |
| **Colorblind Safety** | Not color-only indicators. Add icons, patterns, text labels. | Red/green as only differentiator. Color-only state indicators. |
| **Touch Target (a11y)** | Min 44×44pt interactive area. Expand with padding/hitSlop. | Tiny tap targets without extra padding. Tightly packed elements. |

### 2. Touch & Interaction (CRITICAL)

Mobile-first interaction design that works for fingers, not just mice.

| Rule | Do | Don't |
|------|----|-------|
| **Touch Target Size** | Min 44×44pt iOS / 48×48dp Android. Expand hit area beyond visual bounds. | Small targets. Icon-only without padding. Tight clusters. |
| **Touch Spacing** | Min 8px/8dp gap between touch targets. Prevents mis-taps. | Cramped buttons. Links too close in text. Overlapping regions. |
| **Hover Independence** | Primary actions work with click/tap. Hover is enhancement only. | Hover-only tooltips. Hover-only menus on mobile. |
| **Touch Feedback** | Visual feedback within 100ms of tap (ripple, highlight, opacity). | No touch feedback. Delayed feedback until async completes. |
| **Loading Feedback** | Show state within 100ms. Skeleton >300ms. Disable button during async. | Generic spinner only. No feedback. Double-submit enabled. |
| **Cursor Pointer** | cursor: pointer on all clickable. cursor: not-allowed on disabled. | Missing cursor styles. Pointer on non-interactive elements. |
| **Tap Delay** | touch-action: manipulation to eliminate 300ms mobile tap delay. | Ignoring tap delay. Click-only events on mobile. |
| **Gesture Alternatives** | Visible controls for critical actions. Gestures are shortcuts, not only path. | Swipe-only delete. Multi-finger gestures for primary actions. |
| **System Gestures** | Don't block system gestures (back swipe, Control Center, notifications). | Override system gestures. Interactive elements near screen edges. |
| **Press Feedback** | Visual press state (scale 0.97, opacity change, or ripple effect). | No press state. Layout-shifting press feedback. |
| **Safe Area Awareness** | Keep touch targets away from notch, Dynamic Island, gesture bar. | UI under notches or behind gesture bars. |
| **Drag Threshold** | Movement threshold before drag start. Prevents accidental drags. | Instant drag activation on touch. |

### 3. Performance (HIGH)

Fast loading and smooth interactions directly impact user satisfaction and conversion.

| Rule | Do | Don't |
|------|----|-------|
| **Image Optimization** | WebP/AVIF, responsive srcset/sizes, lazy load non-critical. | Unoptimized PNGs. No responsive images. No dimensions (causes CLS). |
| **Font Loading** | font-display: swap/optional. Preload critical fonts. Subset fonts. | font-display: block (FOIT). All variants loaded. Web fonts for small text. |
| **CLS Prevention** | Reserve space: aspect-ratio for images, min-height for embeds. | Content jumping on load. No space reserved for dynamic content. |
| **Lazy Loading** | Below-fold content, images, route components via Intersection Observer. | Eager load everything. Lazy load above-the-fold content. |
| **Virtual Lists** | Virtualize lists with 50+ items. react-window / @tanstack/virtual. | Render all items. Performance test only with small datasets. |
| **Bundle Splitting** | Code-split by route/feature. Dynamic imports for heavy components. | Single monolithic bundle. Import everything on initial load. |
| **Critical CSS** | Inline critical above-the-fold CSS. Defer non-critical. | Load all CSS at once blocking render. No critical CSS strategy. |
| **Third-party Scripts** | Load async/defer. Audit and remove unnecessary ones. | Sync third-party scripts blocking render. Unaudited dependencies. |
| **Reduce Reflows** | Batch DOM reads then writes. Use transform/opacity for animations. | Frequent layout reads/writes interleaved. Animate layout properties. |
| **Input Latency** | Keep <100ms for taps/scrolling. 60fps (16ms per frame). | Heavy main thread work. Long tasks blocking interaction. |
| **Debounce/Throttle** | Debounce (300ms) for search input. Throttle (100ms) for scroll/resize. | Every keystroke triggers API call. Scroll handler runs expensive code. |
| **Offline Support** | Offline state messaging. Basic fallback UI. Cache critical assets. | Crash on offline. Loading spinner forever. No offline state UI. |

### 4. Style Selection (HIGH)

Choose and apply visual styles consistently across the product.

| Rule | Do | Don't |
|------|----|-------|
| **Style Match** | Match style to product type. Use `--design-system` for recommendations. | Random style choice. Style that conflicts with brand/product purpose. |
| **Consistency** | Same style across all pages and components. Define design tokens. | Mixing styles (glass + flat) arbitrarily. Inconsistent shadow depths. |
| **SVG Icons** | Use vector SVG icons (Heroicons, Lucide, Phosphor). Consistent stroke width. | Emojis as UI icons. Mixed icon sets. Raster PNG icons. |
| **Design Tokens** | Define tokens: colors, spacing, typography, shadows, radius. Use CSS vars. | Hardcoded hex values. Inconsistent spacing. Ad-hoc styling. |
| **Interaction States** | Every element: normal, hover, focus, active, disabled. Smooth transitions. | Missing states. Same style for active/focus. No disabled visual. |
| **Button Hierarchy** | Primary (filled), secondary (outlined), tertiary (text). One primary per view. | Competing primary buttons. No visual distinction between levels. |
| **Platform Adaptation** | Follow iOS HIG or Material Design per platform. Use platform components. | iOS patterns on Android. Custom components vs platform standards. |
| **Elevation Scale** | Define shadow elevation 0-5. Cards=1, modals=3, tooltips=5. | Random shadows. Same elevation everywhere. Flat when depth needed. |
| **Dark Mode** | Design light + dark variants together. Test contrast separately per mode. | Color inversion only. Light mode first, dark as afterthought. |
| **Icon Consistency** | Same stroke width per hierarchy (1.5-2px). One icon set. | Mixed strokes. Filled + outline at same level. Multiple icon families. |

### 5. Layout & Responsive (HIGH)

Design that works on any screen size.

| Rule | Do | Don't |
|------|----|-------|
| **Mobile-First** | Design smallest screen first (375px). Scale up with min-width queries. | Desktop-first squeezing down. max-width mobile queries. |
| **Viewport Meta** | `width=device-width, initial-scale=1`. Never disable zoom. | user-scalable=no. Fixed viewport. |
| **Readable Font Size** | Min 16px body text on mobile. Use rem/em, not px. | Font-size <16px on mobile. px-only sizing. |
| **Horizontal Scroll** | Fit viewport width. overflow-x: hidden on body. Test at 375px. | Fixed-width containers. Long words/code without wrapping. Tables without scroll. |
| **Line Length** | 35-60 chars mobile, 60-75 chars desktop. Use max-width on text. | Full-width text across large screens. Overly narrow columns. |
| **Spacing Scale** | 4pt/8dp incremental system. Tokens: xs(4), sm(8), md(16), lg(24), xl(32). | Arbitrary spacing. Mixed px/rem without scale. Developer-dependent values. |
| **Safe Areas** | Respect notch, Dynamic Island, gesture bar. env(safe-area-inset-*). | UI under notches. Content behind system bars. |
| **Breakpoints** | Test at 375px, 768px, 1024px, 1440px. Defined breakpoint system. | Test desktop only. Device-specific breakpoints. No tablet layout. |
| **Z-Index Scale** | Defined layers: dropdown 100, sticky 200, nav 300, modal 400, toast 500, tooltip 600. | Random z-index: 9999. Stacking context conflicts. |
| **Content Priority** | Critical content first on mobile. Secondary content behind "Show more" / nav. | Everything equally prioritized. Actions below the fold. |
| **Orientation** | Support portrait + landscape. Don't lock unless critical. | Break in landscape. Force portrait only. Hide content in orientation. |
| **Fixed Elements** | Fixed nav/bars must reserve padding for underlying content. Not overlap content. | Fixed bars covering content. No padding for sticky headers. |

### 6. Typography & Color (MEDIUM)

Readable text and purposeful color systems.

| Rule | Do | Don't |
|------|----|-------|
| **Font Pairing** | Complementary pair: expressive headings + readable body. Max 2 families. | >2 families. Two expressive fonts. Similar fonts without contrast. |
| **Line Height** | Body: 1.5-1.75. Headings: 1.2-1.3. Tight for display, spacious for reading. | Line-height <1.4 for body. Tighter than 1 for headings. |
| **Type Scale** | Consistent scale: 12/14/16/18/20/24/32/40/48. Modular scale (1.25 or 1.333). | Random sizes everywhere. No defined scale. Inconsistent proportions. |
| **Semantic Colors** | Define: primary, secondary, success, error, warning, info, surface, on-surface. | Hardcoded hex in components. Names by value (blue) not purpose (primary). |
| **Dark Mode Colors** | Desaturated/lighter tonal variants. Test contrast separately. | Inverted colors. Same contrast assumptions as light mode. |
| **Color Semantics** | Functional colors (error red, success green) include icon/text. Not color-only. | Color-only meaning. Red/green without labels. |
| **Number Formatting** | Tabular/monospaced figures for data columns, prices, timers. | Proportional figures causing layout shift in tables. |
| **Truncation** | Prefer wrapping. Ellipsis with tooltip/expand when needed. | Truncating important content. No way to see full text. |
| **Whitespace** | Intentional whitespace to group related items, separate sections. | Cluttered layouts. No breathing room. Cramped content. |
| **Letter Spacing** | Respect defaults per platform. Tight tracking only for display headings. | Tight tracking on body. Forcing letter spacing on all text. |

### 7. Animation (MEDIUM)

Purposeful motion that enhances — not distracts.

| Rule | Do | Don't |
|------|----|-------|
| **Duration** | Micro-interactions: 150-300ms. Complex: ≤400ms. Exit: 60-70% of enter. | >500ms for UI. Same duration for all. Linear easing. |
| **Performance** | Animate transform + opacity only. Triggers compositing, not layout/paint. | Animate width, height, top, left (triggers layout). |
| **Meaning** | Every animation expresses cause-effect. Spatial continuity. | Decorative-only animation. Motion without purpose. |
| **Easing** | ease-out for entering, ease-in for exiting. Spring/physics for natural feel. | Linear for UI. Ease-in-out for everything. |
| **Reduced Motion** | Respect prefers-reduced-motion. Provide static alternatives. | Ignore motion preferences. Non-stop animation. |
| **Stagger** | List items: 30-50ms stagger. Not all-at-once or too-slow reveals. | Same timing for all items. Stagger >100ms. |
| **State Transitions** | Smooth transitions between states. Not instant snaps. | Button pressed → instant new state. Modal appears without context. |
| **Interruptible** | Animations cancel on user tap/gesture. UI stays interactive. | Blocking input during animation. Non-interruptible sequences. |
| **Shared Elements** | Hero transitions between screens. Maintain spatial continuity. | All transitions are fades. No context for where elements come from. |
| **Modal Motion** | Scale+fade from trigger or slide-in from bottom. Clear direction. | Random entrance direction. Static appearance without context. |

### 8. Forms & Feedback (MEDIUM)

Clear data entry and actionable feedback.

| Rule | Do | Don't |
|------|----|-------|
| **Input Labels** | Visible label per field. Describes what to enter and format. | Placeholder-only label. Labels that disappear on typing. |
| **Error Placement** | Error below the related field. Color + icon + text. | All errors at top only. Color-only error indication. |
| **Submit Feedback** | Loading → success/confirmation or error. Disable on submit. | No loading state. Double-submit possible. Success without confirmation. |
| **Required Indicators** | Mark required fields with asterisk (*). Note: all fields required? Say so. | No indication. Mix of required/optional without legend. |
| **Empty States** | Illustration + message + CTA. Never blank screen. | Generic "No data". Loading forever. Developer errors. |
| **Confirmation** | Confirm destructive actions. Show what will be lost. | "Are you sure?" without context. Immediate irreversible actions. |
| **Progressive Disclosure** | Start simple, reveal complexity on demand. "Advanced" section. | All options upfront. Essential controls hidden in menus. |
| **Inline Validation** | Validate on blur (not keystroke). Error after user finishes typing. | Validation on every keystroke (annoying). Validation only on submit (too late). |
| **Input Type** | type="email/tel/number/url/search" for correct mobile keyboard. | type="text" for all. No inputmode for numeric fields. |
| **Password** | Show/hide toggle. Strength indicator. Allow paste. | No show option. Block paste. Arbitrary character rules. |
| **Autofill** | autocomplete attributes for name, email, address, credit card. Enable password managers. | autocomplete="off" everywhere. Non-standard field names. |
| **Multi-step** | Progress indicator. Back navigation. Step count (Step 2 of 5). | No progress indicator. No back. Lose data on close. |
| **Undo** | Undo for destructive/bulk actions. Toast with 5-10s window. | No undo. Immediate permanent changes. |
| **Error Recovery** | Error says: what happened + why + how to fix + retry. | "Something went wrong" only. No retry. Dismisses permanently. |
| **Toast Notifications** | Auto-dismiss 3-5s. Non-blocking. aria-live="polite". | Require manual dismiss. Infinite stack. Used for critical errors. |

### 9. Navigation Patterns (HIGH)

Users must always know where they are and how to get where they're going.

| Rule | Do | Don't |
|------|----|-------|
| **Bottom Nav** | Max 5 items. Icon + label. Highlight active. Preserve scroll on tab switch. | >5 items. Icon-only. Reset scroll on tab switch. |
| **Back Navigation** | Predictable: previous screen. Restore scroll + input state. | Unexpected destination. Reset form state. Broken back. |
| **Deep Linking** | All screens reachable via deep link. Support universal/app links. | Force start from home. Break links on app update. |
| **Navigation Hierarchy** | Primary (tabs/bottom bar) vs secondary (drawer/settings) clearly separated. | Mixed hierarchy. Navigation changes on different pages. |
| **Tab Bar (iOS)** | Bottom tab bar for top-level navigation. | Tab bar for sub-navigation. More than 5 tabs. |
| **Top Bar (Android)** | Top App Bar with nav icon for primary structure. | Android with bottom-only navigation. No top bar for context. |
| **Search** | Search in top bar or accessible icon. Recent searches, autocomplete, clear button. | Search in menus. No autocomplete. Clear on back. |
| **Drawer Usage** | Drawer for secondary navigation only. Not for primary actions. | Drawer as main navigation. Hiding critical nav in hamburger. |
| **Modal Escape** | Clear close/dismiss affordance. Swipe-down dismiss on mobile. Escape key on web. | No close button. Can't dismiss by clicking outside. |
| **State Preservation** | Navigating back restores scroll position, filters, input. | Reset everything on back. Lose user progress. |
| **Breadcrumbs** | For 3+ level deep hierarchies. Current page not linked. | Missing breadcrumbs in deep pages. Every page has breadcrumbs. |
| **Focus on Route Change** | After navigation, move focus to main content for screen readers. | Focus lost on page change. Screen reader users disoriented. |

### 10. Charts & Data (LOW)

Clear data visualization that tells the story.

| Rule | Do | Don't |
|------|----|-------|
| **Chart Type** | Trend → line. Comparison → bar. Composition → pie (max 5). Distribution → histogram. | Pie for >5 categories. 3D charts (distorts). Area for non-cumulative. |
| **Accessible Colors** | Colorblind-friendly palettes. Patterns + textures supplement color. | Red/green only. Color-only differentiation. |
| **Data Table** | Table alternative for accessibility. Charts alone not screen-reader friendly. | Chart-only data presentation. No tabular fallback. |
| **Tooltips** | On hover/tap with exact values. Keyboard accessible. | Hidden behind chart bounds. Hover-only. No data labels. |
| **Legends** | Always show. Position near chart. Interactive (click to toggle). | Detached far below. Non-interactive. Missing. |
| **Axes Labels** | With units. Readable scale. No truncated/rotated labels on mobile. | Missing units. Cramped ticks. Rotated labels. |
| **Responsive** | Reflow or simplify on small screens. Horizontal bar instead of vertical. | Same layout on all screens. Tiny unreadable charts on mobile. |
| **Empty State** | "No data yet" + guidance. Not blank chart. | Empty chart frame. Loading forever. Error with no retry. |
| **Loading State** | Skeleton/shimmer placeholder. Not empty axis frame. | Generic spinner over chart. Flash of empty chart. |
| **Large Dataset** | Aggregate or sample 1000+ points. Drill-down for detail. | Render all points. Performance crash. Unreadable density. |
| **Direct Labeling** | Label values directly on chart for small datasets. | Legend lookup required for every value. No direct labels. |
| **Number Formatting** | Locale-aware for numbers, dates, currencies. Clear precision. | Inconsistent formatting. Too many decimals. Wrong locale. |

## Example Workflow

**User request:** "Build a landing page for my fintech startup."

### Step 1: Analyze Requirements
- Product type: Fintech / Crypto
- Target audience: Tech-savvy investors
- Style keywords: modern, trustworthy, dark mode optional
- Stack: Next.js + Tailwind

### Step 2: Generate Design System

```bash
node .opencode/skills/shared/search.js "fintech crypto investment" --design-system -p "FinTech App"
```

**Output:** Complete design system with pattern (Trust & Authority), style (Glassmorphism), colors (Financial Trust palette), typography (Inter or Satoshi), and pre-delivery checklist.

### Step 3: Supplement with Detailed Searches

```bash
# Get style details
node .opencode/skills/shared/search.js "glassmorphism dark" --domain style

# UX guidelines for financial apps
node .opencode/skills/shared/search.js "security trust financial" --domain ux-rules

# Chart types for investment dashboard
node .opencode/skills/shared/search.js "financial portfolio" --domain charts
```

### Step 4: Implement
Use Quick Reference categories in priority order:
1. Apply Accessibility rules (contrast, focus, keyboard)
2. Apply Touch & Interaction rules (targets, feedback)
3. Apply Performance rules (images, fonts, lazy loading)
4. Apply Style rules (consistent design tokens)
5. Apply Layout rules (mobile-first, safe areas)
6. Apply Typography & Color rules (semantic colors)
7. Apply Animation rules (purposeful transitions)
8. Apply Forms rules (if registration/auth needed)
9. Apply Navigation rules (predictable structure)
10. Apply Charts rules (if dashboard needed)

### Step 5: Pre-Delivery Checklist

Run through this checklist before marking complete:

**Visual Quality**
- [ ] No emojis used as icons (use SVG instead)
- [ ] All icons from consistent family and stroke width
- [ ] Semantic design tokens used (no hardcoded hex)
- [ ] Button hierarchy clear (primary / secondary / tertiary)
- [ ] Dark mode tested separately (not inferred from light)

**Interaction**
- [ ] All tappable elements have press feedback (ripple/opacity/scale)
- [ ] Touch targets ≥44×44pt (mobile)
- [ ] cursor: pointer on all clickable elements
- [ ] Loading states shown within 100ms
- [ ] Disabled states visually clear and non-interactive

**Accessibility**
- [ ] Color contrast ≥4.5:1 for body text
- [ ] All images have alt text or aria-label
- [ ] Keyboard navigation works fully (Tab, Enter, Escape)
- [ ] Focus indicators visible (not outline: none)
- [ ] Screen reader: heading hierarchy, ARIA landmarks, labels
- [ ] `prefers-reduced-motion` respected

**Layout**
- [ ] Tested at 375px, 768px, 1024px, 1440px
- [ ] Safe areas respected (notch, gesture bar)
- [ ] No horizontal scroll on mobile
- [ ] Font-size ≥16px on mobile body text
- [ ] Consistent 8px/4pt spacing rhythm

**Content & Copy**
- [ ] Error messages explain what happened + how to fix
- [ ] Empty states have illustration + message + CTA
- [ ] CTAs use action verbs ("Save changes" not "Submit")
- [ ] No placeholder-only labels in forms
- [ ] Confirmation before destructive actions

## Common Anti-Patterns Checklist

These frequently reduce perceived quality. Check before delivery:

### Icons & Visual
- [ ] No emojis as structural icons (use Lucide/Heroicons)
- [ ] Vector icons only (no raster PNGs for UI)
- [ ] Consistent stroke width per hierarchy level
- [ ] Icon alignment matches text baseline
- [ ] High contrast icons (4.5:1 for small, 3:1 for large)

### Typography
- [ ] Line-height ≥1.5 for body text
- [ ] Line length ≤75 characters on desktop
- [ ] Type scale follows modular system
- [ ] Font pairing has contrast (serif + sans or distinct weights)
- [ ] No more than 2 font families

### Color
- [ ] Semantic tokens used everywhere (no raw hex in components)
- [ ] Dark mode has independently chosen colors (not inverted)
- [ ] Error/success states include icon + text, not just color
- [ ] Modal scrim opacity 40-60% (not too transparent, not too dark)

### Layout
- [ ] 8px/4pt spacing rhythm consistent
- [ ] Content not hidden behind fixed headers/footers
- [ ] Gutters adapt on larger screens (not same narrow margin everywhere)
- [ ] Z-index scale defined and used consistently

### Interaction
- [ ] Press feedback does not shift layout
- [ ] Micro-interactions 150-300ms with proper easing
- [ ] Gesture regions don't conflict (tap/drag/back-swipe)
- [ ] Disabled controls look disabled (reduced opacity + cursor change)

## Platform-Specific Notes

### iOS (Human Interface Guidelines)
- Use bottom Tab Bar for top-level navigation
- Use Navigation Bar for push navigation
- Support swipe-back gesture (don't disable)
- Use SF Symbols or consistent icon set
- Respect Dynamic Type for text scaling
- Safe areas: notch, Dynamic Island, home indicator
- Haptic feedback for important actions (UIImpactFeedbackGenerator)
- Support Face ID / Touch ID for auth

### Android (Material Design 3)
- Use Top App Bar with navigation icon
- Bottom Navigation (up to 5 items)
- Material You dynamic color theming
- Ripple effect for touch feedback
- Support edge-to-edge display
- Use system back gesture (predictive back)
- Notification channels for granular control

### Web
- Viewport meta with initial-scale=1 (never disable zoom)
- Skip to main content link
- Semantic HTML (header, nav, main, section, article, footer)
- CSS custom properties for theming
- prefers-reduced-motion, prefers-color-scheme, prefers-contrast media queries
- Progressive enhancement (JS optional for critical content)

## Knowledge Reference

- WCAG 2.1 AA/AAA — accessibility standards
- Apple Human Interface Guidelines — iOS/visionOS design
- Material Design 3 — Android/Web design system
- Atomic Design (Brad Frost) — component architecture
- Laws of UX (Jon Yablonski) — psychological principles
- Refactoring UI (Adam Wathan & Steve Schoger) — practical design tips
- Design tokens — cross-platform design consistency
- 8px Grid System — spacing and layout rhythm
- Figma / Sketch — design tools for mockups and prototyping
- Fitts's Law, Hick's Law, Jakob's Law, Miller's Law — UX heuristics
