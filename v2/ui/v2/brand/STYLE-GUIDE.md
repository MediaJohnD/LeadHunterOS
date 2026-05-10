# LeadHunterOS v2 Brand Guide

## Identity
**Name:** LeadHunterOS  
**Voice:** Deterministic lead intelligence. Leads you can audit.  
**Positioning:** An AI SDR command center for operators who require transparent decisions.

## Palette
```
Background:      #FAFAF9   hsl(250 3% 98%)
Surface:         #F5F4F2   hsl(50 11% 96%)
Card:            #FFFFFF   hsl(0 0% 100%)
Border:          #E8E5E0   hsl(40 14% 85%)
Text primary:    #1C1917   hsl(25 11% 10%)
Text secondary:  #44403C   hsl(30 10% 24%)
Accent copper:   #B45309   hsl(22 83% 47%)
Accent light:    #FEF3C7   hsl(47 96% 87%)
Success:         #15803D   hsl(152 69% 24%)
Warning:         #D97706   hsl(38 92% 51%)
Danger:          #B91C1C   hsl(0 84% 47%)
Info:            #0F766E   hsl(170 65% 30%)
Sidebar bg:      #1C1917
Sidebar text:    #F5F4F2
```

## Typography
- Body: DM Sans 400/500/600/700 (base 18px, line-height 1.6)
- Code/Config: DM Mono 400/500
- Self-hosted via package import (`@fontsource`)

## Microcopy Rules
- Prefer specific evidence with date and quantity.
- Explain empty states with next operator action.
- Mark destructive actions with undo window when available.

## Core Classes
- `.lh-card`
- `.lh-sidebar`
- `.lh-btn-primary`
- `.lh-badge-hot`
- `.lh-badge-success`
- `.lh-badge-warning`
- `.lh-badge-danger`

## Integration
```tsx
import "@/v2/brand/globals.css";
import AgentTrajectory from "@/v2/brand/components/AgentTrajectory";
```

## Research-Aligned Validation Checklist
This guide is aligned to widely used marketing science principles (distinctive assets, memory structure reinforcement, category cue clarity, and message consistency). It is not a formal certification by any external institution.

Pass criteria for each release:
- Distinctiveness: Copper accent and warm-neutral UI remain consistent across all key screens.
- Cognitive fluency: Primary actions use plain language and are visible without scrolling on standard laptop viewport.
- Evidence-first messaging: Lead claims always show source/time evidence before score.
- Category clarity: Product purpose is understandable in under 5 seconds by a non-technical operator.
- Trust and control: Every automated action has visible status, retry state, and operator override path.
- Accessibility baseline: Body text >= 18px, clear focus states, and no low-contrast primary controls.

Required UX test set before launch:
- First-run test with non-technical users (no command line usage required).
- Task success test: run objective, inspect trajectory, approve/skip task, export result.
- Error-path test: upstream unavailable, timeout, and partial tool failure with user-readable recovery copy.

## Operator Cost Controls
- Always expose policy controls in-app (no terminal required):
  - minimum signals required for verification
  - max external calls per run
  - cache TTL
  - local-first provider preference
  - semantic recall toggle
- Never present synthetic leads as qualified.
- If qualified data is unavailable, show explicit empty states and recovery guidance.
