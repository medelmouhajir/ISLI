# Plan: Agent Skills as Dedicated Page (like Secrets)

## Goal
Move the inline Skills card from `AgentDetailPage` into a separate full-page interface, mirroring the `AgentSecretsPage` design pattern, while respecting the existing "Neural Command Center" aesthetic and light/dark theme system.

## Current State
- **AgentDetailPage.tsx** has a compact "Skills Card" in the right column (lines 1252–1304) using a `MultiSelect` dropdown.
- **AgentSecretsPage.tsx** is a dedicated route (`/agents/:id/secrets`) with its own header, create form, list view, and empty state.
- **App.tsx** routes are defined explicitly.
- **Theme system** uses CSS custom properties (`--bg-base`, `--accent-cyan`, etc.) switched via `[data-theme="dark"]`.

## Changes

### 1. Create `AgentSkillsPage.tsx`
New component at `isli-board/src/components/AgentSkillsPage.tsx`.

**Layout:**
- Full-page container (`flex-1 overflow-y-auto bg-bg-base`, `max-w-4xl mx-auto`)
- Header with back link (`/agents/:id`), icon (`Wrench`), title "Skill Arsenal", agent ID subtitle
- Stats bar: total available / selected count

**Skill List:**
- Group skills by `category` (same grouping as `MultiSelect`)
- Each skill rendered as a card row:
  - Checkbox toggle (cyan accent when selected)
  - Skill name in `font-mono-data`
  - Type badge (`inline` = amber, `microservice` = cyan)
  - Description text
  - URL hint if available
- Hover state: `hover:bg-bg-elevated/20`
- Selected state: `bg-accent-cyan/10 border-accent-cyan`

**Sticky Footer (Save/Discard):**
- Appears only when selection differs from original
- "Discard" ghost button + "Save Changes" cyan button
- Uses `useUpdateAgent` hook with `onSettled` to reset saving state

**Empty State:**
- `Wrench` icon at 30% opacity
- "No skills registered" message
- Subtitle: "Register skills in Core before assigning them to agents."

**Loading State:**
- Spinner with "Loading available skills..."

### 2. Update `AgentDetailPage.tsx`
- **Remove** the entire "Skills Card" block (lines 1252–1304) from the right column.
- **Add** a "Skills" button in the top action bar (next to Secrets, Memory, Logs, etc.) that navigates to `/agents/:id/skills`.
- Icon: `Wrench` (already imported).
- **Remove** `skillsDirty`, `saveSkills`, `resetSkills`, `skillOptions`, `setSkills`, and `skills` state helpers that are no longer needed in this page.
- Keep `skills` field in `buildForm` for now (it may be used elsewhere), but the UI editing of skills moves out.

### 3. Update `App.tsx`
- Import `AgentSkillsPage`
- Add route: `<Route path="/agents/:id/skills" element={<AgentSkillsPage />} />`

## Design Details

### Token Compliance
All colors use the existing CSS variable system:
- Backgrounds: `bg-bg-base`, `bg-bg-surface`, `bg-bg-elevated/30`
- Borders: `border-border-dim`, `border-accent-cyan` (selected)
- Text: `text-text-primary`, `text-text-secondary`, `text-text-muted`
- Accents: `text-accent-cyan`, `bg-accent-cyan/10`, `shadow-glow-cyan`
- Badges: `bg-accent-amber/10 text-accent-amber` for inline, `bg-accent-cyan/10 text-accent-cyan` for microservice

### Typography
- Section headers: `text-xs font-display font-bold uppercase tracking-widest`
- Skill names: `text-sm font-mono-data font-bold`
- Descriptions: `text-xs text-text-muted`
- Counts/stats: `text-[10px] font-mono-data text-text-muted`

### Icons (lucide-react)
- Page header: `Wrench`
- Empty state: `Wrench`
- Selected check: `Check` (from MultiSelect pattern)
- Back button: `ChevronLeft`
- Save: `Save`

## API Usage
- Fetch agent: `useAgents()` hook (already provides `skills` array)
- Fetch available skills: `useQuery` with `getJSON<SkillMetadata[]>('/v1/skills')` (same as current)
- Update: `useUpdateAgent()` mutate with `{ id, payload: { skills: string[] } }` (same as current `saveSkills`)

## Files Modified
1. `isli-board/src/components/AgentSkillsPage.tsx` — **new**
2. `isli-board/src/components/AgentDetailPage.tsx` — remove skills card, add nav button, clean up dead state
3. `isli-board/src/App.tsx` — add route

## No-Go Areas
- Do not modify `MultiSelect.tsx` (it stays for other uses).
- Do not modify the Core API or skill registry.
- Do not change the theme CSS (`index.css`).
- No new dependencies needed.
