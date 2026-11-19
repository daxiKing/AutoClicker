# AutoClicker roadmap

AutoClicker ships in small, tested milestones. **Shipped** milestones are archived in
the in-app update log; **Next** is the planned scope for the following release;
**Exploring** items are under evaluation and may move, shrink or disappear.

> Legitimate automation only. AutoClicker sends synthetic input and matches pixels on
> your own screen. It does not read game memory, bypass anti-cheat, or implement
> aimbots, aim assist or wallhacks.

## Shipped — v2.5.0 "Orbit"

Automation that watches your workflow.

- **Visual macro timeline editor** — trim a time range, reorder events, nudge
  timestamps by ±10 ms, delete selections and revert, then save the rebuilt timeline.
- **Per-app profiles** — match a foreground window title fragment and apply a saved
  clicker preset automatically while the engine is idle.
- **Scheduled runs** — play a macro at a local time on weekdays, weekends or every day.
  The scheduler checks every 15 seconds, tolerates short sleeps and never fires the
  same occurrence twice.
- **Conditional image sequences** — chain click, key, wait and stop steps. Scan steps
  have a timeout and a skip / retry-forever / hard-stop miss policy.
- **Compact run HUD** — a floating always-on-top status bar with live click, key,
  macro or sequence telemetry and a one-click panic stop.

## Next — v2.6.0 "Pulse"

Smarter flows, fewer gaps.

- **Macro conditionals** — per-event waits, loop counts and if-image-visible branches.
- **Sequence branching** — jump to another step on match or miss instead of running
  linearly to the end.
- **Profile bundles** — export and import app profiles, schedules and macros together.
- **HUD layouts** — compact, expanded and corner-snapped placements.

## Exploring — v2.7.0 "Prism"

See more, script less.

- **Drag-selected scan regions** across multiple monitors.
- **OCR triggers** for menus, chat and HUD text.
- **Opt-in, local-first cloud sync** for the macro vault.
- **Plugin hooks** for community steps and actions.

## How items get promoted

1. An exploring item needs a clear, testable definition and a UI-free core module.
2. Core logic lands with functional tests before any page wiring.
3. A milestone ships when Windows and Linux packages build in CI, the installer
   upgrades cleanly and the release notes are published to GitHub and itch.io.

## Release history

| Version | Codename | Date | Headline |
| --- | --- | --- | --- |
| 2.5.0 | Orbit | 2026-11-19 | Macro editor, app profiles, scheduled runs, image sequences, run HUD |
| 2.4.0 | Nebula | 2026-11-17 | Rebuilt engines, Discord Rich Presence, Explore, 43 languages, Linux |
| 2.3.0 | Atlas | 2026-11-17 | Presence, languages, Explore and GitHub updates |
| 2.2.0 | Kaleidoscope | 2026-11-16 | Image-target library remaster |
| 2.1.1 | Service Pack | 2026-11-16 | Esc-to-unbind hotkeys, wider image formats |
| 2.1.0 | Solid State | 2026-11-16 | AutoClicker rebrand, presets, window picker |
| 2.0.0 | Overdrive | 2026-11-16 | Auto-stop, click sound, window filter, macro import/export |
| 1.0.0 | Ignition | 2026-11-15 | First stable release |
| 0.9.0 | Blueprint | 2026-11-02 | Input pipeline proof of concept |
