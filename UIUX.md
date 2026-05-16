# UI/UX Design Document
## ARGUS Sentinel — Intelligence Dashboard

**Version:** 1.0  
**Date:** 2026-05-16

---

## 1. Design Philosophy

ARGUS Sentinel's visual language is built on one idea: **signal clarity in the dark**.

Intelligence tools are used by analysts working under time pressure who need to understand critical information instantly. Every design decision prioritises:

1. **Immediate comprehension** — key metrics visible in under 3 seconds
2. **Confidence communication** — probability scores conveyed visually, not just numerically
3. **Alert hierarchy** — danger surfaces immediately, routine data stays calm
4. **Zero cognitive load for navigation** — no menus to hunt through

The aesthetic draws from satellite imagery software, OSINT platforms, and financial terminal design — purposeful, data-dense, and dark.

---

## 2. Design Tokens

### 2.1 Colour System

```css
/* Background layers */
--bg:       #0a0c10   /* Canvas — deepest level */
--surface:  #111318   /* Cards, panels, header */
--surface2: #1a1d24   /* Nested elements, inputs */

/* Borders */
--border:   rgba(255,255,255,0.07)   /* Default dividers */
--border2:  rgba(255,255,255,0.14)   /* Interactive elements */

/* Typography */
--text:   #e8eaf0   /* Primary — body text */
--text2:  #8b8fa8   /* Secondary — labels, metadata */
--text3:  #555970   /* Tertiary — placeholders, hints */

/* Semantic colours */
--accent:  #5b8df8   /* Primary action, links, progress */
--accent2: #3d6ee8   /* Hover state */
--green:   #38d98a   /* Positive, success, low velocity */
--amber:   #f5a623   /* Warning, medium velocity */
--coral:   #f07060   /* Elevated warning, high velocity */
--red:     #e84040   /* Alert, peak velocity, danger */
--teal:    #2ec4b6   /* Site watcher badge */
--purple:  #a78bfa   /* Social/signal miner badge */

/* Monospace font */
--mono: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace
```

### 2.2 Velocity Score Colour Mapping

| Score Range | Colour | CSS Class | Meaning |
|-------------|--------|-----------|---------|
| 0.0 – 2.9 | `--text2` (#8b8fa8) | `.score-low` | Baseline / quiet |
| 3.0 – 4.9 | `--amber` (#f5a623) | `.score-medium` | Elevated — watch |
| 5.0 – 7.9 | `--coral` (#f07060) | `.score-high` | High — monitor closely |
| 8.0 – 10.0 | `--red` (#e84040) | `.score-peak` | Peak — immediate action |

### 2.3 Source Badge Colours

| Source | Background | Text | Border |
|--------|-----------|------|--------|
| NEWS | `rgba(91,141,248,0.15)` | `--accent` | `rgba(91,141,248,0.3)` |
| FINANCE | `rgba(56,217,138,0.12)` | `--green` | `rgba(56,217,138,0.25)` |
| SITE | `rgba(46,196,182,0.12)` | `--teal` | `rgba(46,196,182,0.25)` |
| SOCIAL | `rgba(167,139,250,0.12)` | `--purple` | `rgba(167,139,250,0.25)` |

### 2.4 Typography Scale

| Role | Size | Weight | Color |
|------|------|--------|-------|
| Logo | 16px | 600 | `--text` |
| Card title | 13px | 600 | `--text2` (uppercase, 0.06em tracking) |
| Composite velocity score | 44px | 700 | velocity-class |
| Source velocity score | 28px | 600 | velocity-class |
| Body text | 14px | 400 | `--text` |
| Signal content | 13px | 400 | `--text` |
| Labels / metadata | 11–12px | 400–600 | `--text2` / `--text3` |
| Badge text | 10px | 600 | source-class (uppercase) |

### 2.5 Spacing & Radius

| Token | Value |
|-------|-------|
| Card border-radius | 10px |
| Button border-radius | 8px |
| Badge border-radius | 4px |
| Card padding | 16px 20px |
| Layout gap (main/side) | 24px padding each side |
| Section gap | 16px margin-bottom |

---

## 3. Layout Architecture

### 3.1 Desktop Layout (1280px+)

```
┌─────────────────────────────────────────────────────────────┐
│ HEADER (sticky, 64px)                                       │
│ [🛰 ARGUS Sentinel] [Temporal Web Intelligence]   [● Live] │
├─────────────────────────────────────────────────────────────┤
│ QUERY BAR (56px)                                            │
│ [___________________________Query input___________________] │
│ [                                            Run Intelligence]│
├───────────────────────────────────┬─────────────────────────┤
│ MAIN PANEL (flex: 1)              │ SIDEBAR (340px)         │
│                                   │                         │
│  [Velocity Card]                  │ Intelligence History    │
│  [Prediction Card]                │ ┌─────────────────────┐ │
│  [Signals Card]                   │ │ Query text          │ │
│  [Executive Summary Card]         │ │ ⚡ 8.7  ALERT  9:32 │ │
│                                   │ └─────────────────────┘ │
└───────────────────────────────────┴─────────────────────────┘
```

### 3.2 Column Proportions
- Main panel: `1fr` (auto-fills available space)
- Sidebar: `340px` fixed
- Total gap: `1px solid var(--border)` divider

### 3.3 Responsive Breakpoints (Improvement over v1)

| Breakpoint | Behaviour |
|-----------|----------|
| < 768px (mobile) | Single column, sidebar collapses to bottom drawer |
| 768–1024px (tablet) | Single column, sidebar hidden, history button in header |
| 1024px+ (desktop) | Full two-column layout |

---

## 4. Component Specifications

### 4.1 Header

```
[🛰 logo-icon] [ARGUS Sentinel] [Temporal Web Intelligence]  ··········  [● Connected]
```

- Logo icon: 32px × 32px, 8px radius, gradient `--accent → --purple` (135°)
- Status dot: 8px circle — grey (disconnected), green glowing (connected), amber pulsing (running)
- Status label: 12px `--text2`, right-aligned

### 4.2 Query Bar

- Input: `border: 1px solid var(--border2)` at rest → `border-color: var(--accent)` on focus
- Placeholder suggests 4 example query types
- Run button: `background: var(--accent)` → `var(--accent2)` on hover, scales to 0.97 on click
- Keyboard shortcut: `Enter` submits query

**Example chip buttons (empty state):**
- `OpenAI product signals`
- `Stripe M&A signals`
- `Anthropic vs DeepMind hiring`
- `Notion competitor pricing changes`

### 4.3 Empty State

Centred vertically in main panel:
- Large satellite emoji (48px, 30% opacity)
- Title: 16px `--text2`
- Description: 13px `--text3`, max-width 340px
- Example chips below description

### 4.4 Processing State

Four-step pipeline progress indicator:
```
[Spinner]
○ Parsing query intent
● Deploying 4 agents (news, finance, site, social)   ← active (animated dot)
○ Running temporal velocity engine
○ Synthesising with Claude + MCP live web
```

- Completed steps: green dot + green text
- Active step: accent-colour dot (pulsing) + white text
- Pending steps: grey dot + `--text2` text

### 4.5 Velocity Card

```
┌─────────────────────────────────────────────────────┐
│ 🎯 Entity — OpenAI                       09:32:11   │
│                                                     │
│  8.7          Trajectory ↑ accelerating             │
│  /10          ▁▃▅▇█ (sparkline)                    │
│ composite                                           │
│                                                     │
│  [7.2]  [9.1]  [5.4]  [8.8]                       │
│  news   finance  site  social                       │
│  velocity velocity velocity velocity               │
└─────────────────────────────────────────────────────┘
```

**Sparkline spec:**
- SVG polyline, 200×36px
- Point colour: red if last ≥ 5, amber if last ≥ 3, else accent blue
- Endpoint dot: 3px filled circle in same colour
- Stroke-width: 1.5px, linejoin: round

### 4.6 Prediction Card

```
┌─────────────────────────────────────────────────────┐
│ 🔮 Prediction                                       │
│ ┌───────────────────────────────────────────────┐  │
│ │ High probability of a major model              │  │
│ │ announcement within 14 days                   │  │
│ │                                               │  │
│ │ ████████████████░░░░ 82%  confidence          │  │
│ └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

- Confidence bar: 4px height, `var(--border2)` background → `var(--accent)` fill
- Bar width animates over 0.8s ease transition
- Percentage in `var(--accent)` bold text

### 4.7 Signals Card

```
┌─────────────────────────────────────────────────────┐
│ 📡 Top signals                                      │
│ ─────────────────────────────────────────────────  │
│ [NEWS]   3× increase in GPT-5 mentions in 48h       │
│          weight: 0.91                               │
│ ─────────────────────────────────────────────────  │
│ [FINANCE] Azure AI compute spend +40% in Q1 filing  │
│           weight: 0.88                              │
│ ─────────────────────────────────────────────────  │
│ [SOCIAL]  OpenAI eng team sentiment: excitement peak│
│           weight: 0.75                              │
└─────────────────────────────────────────────────────┘
```

- Source badge: small pill, 10px uppercase text, colour per source table
- Signal content: 13px, max 160 chars displayed
- Weight: 11px `--text3`
- Max 6 signals shown

### 4.8 Alert Banner

```
┌─────────────────────────────────────────────────────┐
│ ⚠  Alert triggered — velocity threshold exceeded.   │
│    Immediate attention recommended.                 │
└─────────────────────────────────────────────────────┘
```

- `background: rgba(232,64,64,0.12)` + `border: 1px solid rgba(232,64,64,0.3)`
- Appears at top of report section when `alert_triggered === true`

### 4.9 Executive Summary Card

```
┌─────────────────────────────────────────────────────┐
│ 📋 Executive summary                               │
│                                                    │
│ [Summary paragraph text]                           │
│                                                    │
│ KEY FINDINGS                                       │
│ → Finding 1                                        │
│ → Finding 2                                        │
│                                                    │
│ RECOMMENDED ACTIONS                                │
│ → Action 1 (green)                                 │
│ → Action 2 (green)                                 │
└─────────────────────────────────────────────────────┘
```

### 4.10 History Feed (Sidebar)

```
Intelligence history

┌─────────────────────────────────────────┐
│ OpenAI product signals                  │
│ ⚡ 8.7  [ALERT]                  09:32 │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│ Stripe M&A signals                      │
│ ⚡ 4.2                           08:17 │
└─────────────────────────────────────────┘
```

- Click on history item re-renders that report in main panel
- ALERT badge: `--red` text on `rgba(232,64,64,0.12)` background, 10px
- Score coloured by velocity class

---

## 5. Interaction Design

### 5.1 Query Submission Flow

```
User types query → presses Enter / clicks Run
  → Button disabled, text → "Running…"
  → Status dot → amber pulsing
  → Empty/previous state hidden
  → Processing state shown with step animation
  
Pipeline steps animate sequentially via WebSocket:
  status: "running"          → Step 1 active
  status: "agents_deployed"  → Step 1 done, Step 2 active
  (step 3 and 4 activate on completion)
  type: "report"             → Processing hidden, report shown
  → Status dot → green
  → Button re-enabled
```

### 5.2 WebSocket Reconnection

Client auto-reconnects after 3s on disconnect. Status indicator shows "Reconnecting…" during gap. History replayed on reconnect.

### 5.3 History Feed Interaction

- Clicking a history item instantly renders the cached report (no new query)
- Items appear newest-first
- Placeholder text removed on first item

---

## 6. Animations

| Animation | Property | Duration | Easing |
|-----------|----------|----------|--------|
| Status dot pulse | opacity | 1s | `0%,100%: 1; 50%: 0.4` |
| Spinner | rotation | 0.8s | linear infinite |
| Confidence bar fill | width | 0.8s | ease |
| Button press | scale | instant | scale(0.97) |
| Card hover (sidebar) | border-color | 0.15s | ease |

---

## 7. Accessibility

- All interactive elements have visible focus states
- Colour is never the sole indicator (badges have text labels too)
- Alert uses emoji icon + text, not colour alone
- Minimum contrast ratios: body text (`--text` on `--surface`) > 7:1
- Font sizes minimum 11px for metadata labels

---

## 8. Design Improvements Over v1

| Area | v1 Current | Improvement |
|------|-----------|-------------|
| **Mobile** | Not responsive | Add breakpoints, collapsible sidebar |
| **Multi-entity** | Only first profile shown in UI | Tab navigation for multiple entity profiles |
| **Charts** | Mini sparkline only | Expandable velocity timeline chart |
| **Export** | None in UI | "Download Report" button (JSON + future PDF) |
| **Watch Mode** | CLI only | Watch mode toggle in dashboard with interval selector |
| **Settings** | Config file only | In-dashboard threshold configuration |
| **Dark/Light** | Dark only | Theme toggle |
| **Loading text** | Generic steps | Live agent status updates (e.g., "NewsAgent: 14 signals") |

---

## 9. Design System File Structure (Future)

```
design/
├── tokens.css          # CSS custom properties
├── components/
│   ├── badge.css       # Source badges
│   ├── card.css        # Card variants
│   ├── velocity.css    # Velocity gauges + sparkline
│   └── alert.css       # Alert banner
├── layouts/
│   ├── header.css
│   ├── query-bar.css
│   └── main-sidebar.css
└── pages/
    └── dashboard.html  # Full assembled page
```
