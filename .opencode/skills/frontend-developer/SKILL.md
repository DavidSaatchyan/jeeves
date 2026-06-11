---
name: frontend-developer
description: "Professional frontend engineer for React, Vue, Angular, Svelte, and web platforms. Includes 80+ component patterns, 50+ React hooks patterns, 30+ performance rules, 25+ accessibility patterns, 20+ state management patterns, 15+ animation rules, and 10+ CSS architecture patterns. Covers Next.js, Nuxt, Remix, TanStack, Tailwind, shadcn/ui, Framer Motion, React Query, Zustand, and more. Actions: build, create, implement, refactor, optimize, fix, review. Elements: component, hook, page, layout, modal, form, table, chart, navigation, animation. Topics: state management, data fetching, performance, accessibility, styling, testing, bundling."
license: MIT
compatibility: opencode
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: frontend
  triggers: UI, frontend, component, React, Vue, Angular, Svelte, Next.js, Nuxt, CSS, Tailwind, JavaScript, TypeScript, state management, hook, responsive, a11y, animation
  role: specialist
  scope: implementation
  output-format: code
  related-skills: ux-designer, test-master, security-engineer, architecture-designer, backend-developer
---

# Frontend Developer Pro — Component Engineering

Senior frontend engineer specializing in component architecture, state management, data fetching, performance optimization, and accessible UI. Covers React 18/19, Vue 3, Angular 17+, and Svelte 5 with framework-specific patterns.

## Framework Decision Matrix

| Need | React | Vue | Angular | Svelte |
|------|-------|-----|---------|--------|
| Ecosystem size | Largest | Large | Large | Growing |
| Bundle size | Medium | Small | Large | Smallest |
| Learning curve | Medium | Low | High | Low |
| SSR/SSG | Next.js, Remix | Nuxt | Angular Universal | SvelteKit |
| State management | Zustand, Redux, Jotai | Pinia | NgRx/Signals | Svelte stores |
| Performance | Medium | Good | Good | Best |
| Mobile | React Native | NativeScript | NativeScript | Svelte Native |
| TypeScript | Excellent | Good | Built-in | Good |
| When to choose | Ecosystem, jobs, RN | Simplicity, rapid dev | Enterprise, opinions | Performance, simplicity |

## Quick Reference — 12 Priority Categories

### 1. Component Architecture (CRITICAL)

Every component must handle loading, empty, error, and edge cases.

| Pattern | Rule | Do | Don't |
|---------|------|----|-------|
| **Directory Structure** | Feature-based organization | `features/auth/components/`, `shared/ui/Button.tsx` | Flat `components/` folder with hundreds of files |
| **Component Size** | One component = one responsibility | Max 200 lines, extract sub-components | 500+ line components doing everything |
| **Props Interface** | Explicit typed props | `interface Props { items: Item[]; onSelect: (id: string) => void }` | `any` props, untyped callbacks |
| **States** | Every data component | loading skeleton + empty message + error + success | Only happy path, no loading/error/empty |
| **Composition** | Prefer composition over props | `children` + slots for flexibility | Boolean props for layout variants |
| **Custom Hooks** | Extract logic from UI | `useUser()`, `useItems()` → clean components | Logic mixed with JSX, unextracted side effects |
| **Server Components** | RSC by default, client when needed (Next.js) | `"use client"` only for interactive, state, effects | Everything is client component |
| **Error Boundaries** | Catch render errors | `ErrorBoundary` with fallback UI per section | No error boundaries, white screen on crash |
| **Suspense Boundaries** | Loading fallback per section | `<Suspense fallback={<Skeleton />}>` | One loader for entire page |

### 2. TypeScript & Type Safety (HIGH)

Every component, hook, and utility must be typed.

| Rule | Do | Don't |
|------|----|-------|
| **Props Typing** | Named interface Props exported | `export interface Props { ... }` | Inline types, `any`, repeated types |
| **Event Handlers** | Typed callback signatures | `onChange: (value: string) => void` | `onChange: Function` or `onChange: any` |
| **Generics** | Reusable typed utilities | `function useList<T>(items: T[])` | Type casting, type assertions |
| **Null Safety** | Handle undefined/null explicitly | `??` default, optional chaining `?.` | `undefined is not an object` errors |
| **Discriminated Unions** | For variant states | `type State = { status: 'loading' } \| { status: 'error'; error: Error }` | Boolean flags for states |
| **as const** | Literal types | `const roles = ['admin', 'user'] as const` | String literals without const assertion |
| **satisfies** | Type validation without widening | `const config = { ... } satisfies Config` | `as Config` (loses inference) |

### 3. State Management (HIGH)

Choose the right state solution for each concern.

| Concern | Solution | When | Don't |
|---------|----------|------|-------|
| **Server data** | TanStack Query / SWR / RTK Query | Any async data from API | Put server data in global state |
| **Global UI state** | Zustand / Context + useReducer / Jotai | Theme, auth status, sidebar | Single Redux store for everything |
| **Form state** | React Hook Form + Zod / Formik | Any form more than 3 fields | useState for every field |
| **URL state** | useSearchParams / next/navigation | Filters, pagination, search query | Duplicate URL in state |
| **Local state** | useState / useReducer | Component-scoped: toggle, input value | Global context for local state |
| **Derived state** | useMemo / computed | Filtered/sorted lists, computed values | Recalculate on every render |
| **Atomic state** | Jotai / Recoil | Complex interdependent state | Prop drilling through 5+ levels |

**React Query patterns:**
```typescript
// Fetch
const { data, isLoading, error } = useQuery({
  queryKey: ['items', filters],
  queryFn: () => api.getItems(filters),
  staleTime: 30_000, // 30s before refetch
  gcTime: 5 * 60_000, // 5min cache
})

// Mutation with optimistic update
const mutation = useMutation({
  mutationFn: api.updateItem,
  onMutate: async (newItem) => {
    await queryClient.cancelQueries({ queryKey: ['items'] })
    const previous = queryClient.getQueryData(['items'])
    queryClient.setQueryData(['items'], (old) => old.map(i => i.id === newItem.id ? { ...i, ...newItem } : i))
    return { previous }
  },
  onError: (err, newItem, context) => {
    queryClient.setQueryData(['items'], context.previous)
  },
})
```

### 4. Performance Optimization (HIGH)

| Rule | Pattern | Implementation |
|------|---------|----------------|
| **Memo Components** | Pure display components | `React.memo(ExpensiveList)` with props comparison |
| **Memo Hooks** | Expensive calculations | `useMemo(() => compute(items), [items])` — only when cost > 1ms |
| **Callback Stability** | Stable callback refs | `useCallback(fn, [deps])` for children using React.memo |
| **Virtual Lists** | 50+ items | `@tanstack/virtual`, `react-window`, or CSS `content-visibility: auto` |
| **Lazy Loading** | Route-level | `React.lazy(() => import('./HeavyPage'))` + `<Suspense>` |
| **Image Optimization** | next/image or manual | `<Image>` with width/height, lazy loading, WebP |
| **Bundle Analysis** | Find bloat | `npx vite-bundle-analyzer` or `next-bundle-analyzer` |
| **Debounce** | Search / input | 300ms debounce for search, 150ms for resize |
| **Throttle** | Scroll / resize | 100ms throttle for scroll handlers |
| **Avoid Unnecessary Renders** | Component isolation | Split large components, move state down |
| **CSS Container Queries** | Responsive components | `@container (min-width: 400px)` — better than window-based |
| **content-visibility** | Below-fold sections | `content-visibility: auto; contain-intrinsic-size: 500px` |

### 5. Accessibility (HIGH)

Every component must be accessible by default.

| Pattern | Implementation | Testing |
|---------|----------------|---------|
| **Semantic HTML** | `<button>`, `<nav>`, `<main>`, `<aside>`, `<form>` — not div soup | Axe DevTools, Lighthouse a11y audit |
| **Focus Management** | Visible focus ring (2px offset), tabIndex, focus trapping in modals | Keyboard-only navigation test |
| **ARIA Labels** | `aria-label` on icon buttons, `aria-describedby` for descriptions | VoiceOver / NVDA test |
| **Color Contrast** | 4.5:1 body, 3:1 large text. `prefers-contrast: more` support | Contrast checker tools |
| **Keyboard** | Tab, Enter, Escape, Arrow keys for all interactive elements | Tab through entire page |
| **Reduced Motion** | `@media (prefers-reduced-motion: reduce)` → disable/scale down | DevTools: emulate prefers-reduced-motion |
| **Screen Reader** | `aria-live="polite"` for dynamic updates, proper heading hierarchy | VoiceOver rotor check |
| **Skip Link** | First focusable element: skip to main content | Tab on page load |
| **Form Accessibility** | Labels with for/id, fieldset/legend for groups | Screen reader form test |

### 6. Styling & CSS Architecture (HIGH)

| Approach | When | Example |
|----------|------|---------|
| **Tailwind CSS** | Rapid development, design system from CSS | Default choice for most projects |
| **CSS Modules** | Component-scoped, zero runtime | `*.module.css` with unique class names |
| **CSS-in-JS** | Dynamic styles, theming | styled-components, Emotion (avoid if possible) |
| **CSS Variables** | Theming, design tokens | `--color-primary: #2563eb; color: var(--color-primary)` |
| **Panda CSS** | Type-safe CSS, zero runtime | Modern Tailwind alternative with runtime CSS |
| **Vanilla Extract** | Type-safe, build-time | Zero-runtime CSS with TypeScript |

**CSS Architecture Rules:**
```css
/* Design tokens — global */
:root {
  --color-primary: #2563eb;
  --color-surface: #ffffff;
  --spacing-sm: 0.5rem;
  --spacing-md: 1rem;
  --radius-sm: 0.375rem;
  --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.05);
}

/* Component — scoped, token-based */
.btn {
  background: var(--color-primary);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-sm);
}

/* Responsive — container queries preferred */
@container (min-width: 400px) {
  .card { display: grid; grid-template-columns: 1fr 1fr; }
}
```

### 7. Data Fetching & Side Effects (HIGH)

| Concern | Pattern | Implementation |
|---------|---------|----------------|
| **API calls** | TanStack Query / SWR | Automatic caching, refetching, dedup |
| **Mutations** | useMutation | Optimistic updates, rollback on error |
| **Infinite scroll** | useInfiniteQuery | `getNextPageParam`, intersection observer |
| **WebSockets** | Custom hook or library | `useWebSocket(url)` with reconnect |
| **Polling** | refetchInterval | `refetchInterval: 30000` for near-real-time |
| **Prefetching** | queryClient.prefetchQuery | Hover/intersection observer prefetch |
| **Parallel queries** | useQueries | Multiple independent queries in parallel |
| **Dependent queries** | enabled option | `enabled: !!userId` wait for dependency |

**Streaming / SSR patterns (Next.js):**
```typescript
// Server Component with streaming
async function Page() {
  const data = await fetchData() // Suspense boundary handles loading
  return <Items data={data} />
}

// Parallel data fetching
async function Page() {
  const [user, items] = await Promise.all([
    fetchUser(),
    fetchItems(),
  ])
  return <Dashboard user={user} items={items} />
}
```

### 8. Forms & Validation (MEDIUM)

| Pattern | Implementation |
|---------|----------------|
| **Library choice** | React Hook Form (React), vee-validate (Vue) |
| **Schema validation** | Zod / Yup schemas shared frontend+backend |
| **Controlled vs uncontrolled** | Uncontrolled by default, controlled when needed |
| **Async validation** | `validate: async (value) => check(value)` |
| **Error display** | Error message below field, icon + text |
| **Form state** | `isDirty`, `isSubmitting`, `isValid` for UX |
| **File uploads** | Dropzone component + progress |

```typescript
const schema = z.object({
  email: z.string().email('Invalid email'),
  password: z.string().min(8, 'Min 8 characters'),
})

type FormData = z.infer<typeof schema>

function LoginForm() {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  })

  return (
    <form onSubmit={handleSubmit(api.login)}>
      <input {...register('email')} aria-invalid={!!errors.email} />
      {errors.email && <span role="alert">{errors.email.message}</span>}
      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Logging in...' : 'Login'}
      </button>
    </form>
  )
}
```

### 9. Animation & Transitions (MEDIUM)

| Pattern | Library | When |
|---------|---------|------|
| **Layout animations** | Framer Motion `AnimatePresence` | Enter/exit animations for lists, modals |
| **Page transitions** | Framer Motion / Nuxt page transitions | Route change animations |
| **Scroll animations** | Intersection Observer + CSS | Reveal on scroll, parallax |
| **Micro-interactions** | CSS transitions | Hover, focus, press states (150-300ms) |
| **Stagger list** | Framer Motion `variants` | List items with 30-50ms delay |
| **Shared layouts** | Framer Motion `layoutId` | Hero/image transitions between pages |
| **Drag** | Framer Motion `drag` | Sortable lists, swipeable cards |

```typescript
// Framer Motion — enter/exit
<AnimatePresence mode="wait">
  <motion.div
    key={currentPage}
    initial={{ opacity: 0, x: 20 }}
    animate={{ opacity: 1, x: 0 }}
    exit={{ opacity: 0, x: -20 }}
    transition={{ duration: 0.2 }}
  >
    {children}
  </motion.div>
</AnimatePresence>
```

### 10. Testing (HIGH)

| Test Type | Framework | Coverage |
|-----------|-----------|----------|
| **Unit** | Vitest / Jest + Testing Library | Pure functions, hooks, utilities |
| **Component** | Testing Library | Render + interaction + state; test behavior, not implementation |
| **Integration** | Vitest + msw | API calls + state updates |
| **E2E** | Playwright / Cypress | Critical user flows |
| **Visual regression** | Chromatic / Percy | Screenshot diff on visual changes |
| **Accessibility** | axe-core / Testing Library a11y | Automated a11y checks |

```typescript
// Component test (Testing Library)
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

test('submits form with valid data', async () => {
  const onSubmit = vi.fn()
  render(<LoginForm onSubmit={onSubmit} />)

  await userEvent.type(screen.getByLabelText('Email'), 'test@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'ValidPass1')

  await userEvent.click(screen.getByRole('button', { name: /login/i }))

  expect(onSubmit).toHaveBeenCalledWith({
    email: 'test@example.com',
    password: 'ValidPass1',
  })
})
```

### 11. Build & Bundling (MEDIUM)

| Tool | When | Don't |
|------|------|-------|
| **Vite** | Default for React/Vue/Svelte | Override default config without reason |
| **Turbopack** | Next.js dev (faster HMR) | Use in production yet |
| **Webpack** | Legacy projects only | Start new projects with Webpack |
| **esbuild** | Build tooling (plugins, scripts) | Replace bundler entirely |
| **SWC** | Fast compilation | Use Babel for new projects |

**Bundle optimization:**
```typescript
// Dynamic import
const Chart = dynamic(() => import('./Chart'), {
  loading: () => <Skeleton className="h-96" />,
  ssr: false, // if chart needs window
})
```

### 12. Security (MEDIUM)

| Vulnerability | Prevention |
|---------------|-----------|
| **XSS** | React/Vue/Svelte auto-escape by default. DangerouslySetInnerHTML = last resort |
| **CSRF** | SameSite cookies, CSRF tokens on forms |
| **Sensitive data** | Don't store tokens in localStorage (use httpOnly cookies) |
| **Dependencies** | Regular `npm audit`, Dependabot, Snyk |
| **Auth tokens** | httpOnly cookies, short expiry (15min access, 7d refresh) |

## Component Template (React)

```typescript
interface Props<T> {
  items: T[]
  onSelect: (id: string) => void
  isLoading?: boolean
  error?: Error | null
}

function ItemList<T extends { id: string; name: string }>({
  items, onSelect, isLoading, error
}: Props<T>) {
  if (isLoading) return <Skeleton count={5} />
  if (error) return <ErrorState message={error.message} onRetry={() => window.location.reload()} />
  if (items.length === 0) return <EmptyState message="No items found" action="Add your first item" />

  return (
    <ul role="list">
      {items.map(item => (
        <li key={item.id}>
          <button onClick={() => onSelect(item.id)}>
            {item.name}
          </button>
        </li>
      ))}
    </ul>
  )
}

export default React.memo(ItemList) as typeof ItemList
```

## Pre-Delivery Checklist

### Code Quality
- [ ] All components typed (Props interface, no `any`)
- [ ] No console.log, debugger, or TODO comments
- [ ] Loading / empty / error states for all data components
- [ ] Error boundaries at section level
- [ ] Custom hooks for reusable logic

### Performance
- [ ] No unnecessary re-renders (React DevTools profiler check)
- [ ] Images have width/height (no CLS)
- [ ] Routes code-split, heavy components lazy-loaded
- [ ] Lists with 50+ items virtualized
- [ ] Search inputs debounced

### Accessibility
- [ ] Keyboard navigation works fully
- [ ] Focus indicators visible
- [ ] Alt text on images, aria-labels on icon buttons
- [ ] Color contrast ≥4.5:1
- [ ] Screen reader test (VoiceOver/NVDA)

### Styling
- [ ] Design tokens used (no hardcoded values)
- [ ] Responsive: 375px, 768px, 1024px, 1440px tested
- [ ] Dark mode supported and tested
- [ ] CSS no unused / no bundle bloat

### Testing
- [ ] Unit tests for hooks and utilities
- [ ] Component tests for critical UI (renders, interactions)
- [ ] E2E test for main user flow
- [ ] Tests pass in CI

## Framework-Specific Patterns

### Next.js (App Router)
- Server components by default, `"use client"` only when needed
- `layout.tsx` for shared UI, `page.tsx` for routes
- `loading.tsx` for Suspense, `error.tsx` for errors
- `generateMetadata()` for SEO
- `server-only` / `client-only` for environment isolation

### Vue 3 (Composition API)
- `defineProps` + `defineEmits` for typed components
- Composables (`useAuth()`) = Vue equivalent of hooks
- `<script setup lang="ts">` preferred
- `v-model` for two-way binding
- Slots for component composition
- Pinia for global state

### Angular 17+
- Standalone components (no NgModule needed)
- `@Input()` + `@Output()` for component API
- Signals for reactive state (`signal()`, `computed()`, `effect()`)
- `@if` / `@for` / `@switch` control flow
- `inject()` for DI (no constructor injection needed)

### Svelte 5 (Runes)
- `$state()`, `$derived()`, `$effect()` runes
- `$props()` for component inputs
- Snippets (`{#snippet name()}`) for template composition
- Stores for shared state (or `$state` in module)
- `svelte:head` for metadata

## Knowledge Reference

- React 18/19, Next.js 14/15, TanStack Query, Zustand, React Hook Form + Zod, Framer Motion
- Vue 3, Nuxt 3, Pinia, vee-validate, VueUse
- Angular 17+, Signals, NgRx, Angular Material
- Svelte 5, SvelteKit, Svelte stores
- TypeScript, Tailwind CSS, CSS Modules, Panda CSS
- Vitest, Testing Library, Playwright
- Vite, Turbopack, SWC
- WCAG 2.1 AA, WAI-ARIA, Apple HIG, Material Design 3
