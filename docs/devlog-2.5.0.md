## AutoClicker v2.5.0 — Orbit is out now

AutoClicker v2.5.0 "Orbit" turns the console into an automation hub. Build visual
workflows, react to the app you are using, run macros on a clock and keep an eye on
everything from a compact floating HUD.

### What's new in 2.5.0

- **Visual macro editor** — open any recording and trim a time range, reorder events,
  nudge timestamps by ±10 ms, delete selections or revert. The timeline is rebuilt and
  saved in one step.
- **App profiles** — match a foreground window title fragment to a saved clicker preset.
  The preset applies automatically while the click engine is idle, and "Use active
  window" fills the match field for you.
- **Scheduled runs** — play a macro at a local time on weekdays, weekends or every day.
  The scheduler checks every 15 seconds and remembers which occurrence already fired.
- **Conditional image sequences** — chain steps that click a target, press a key, wait or
  stop. Every scan step has a timeout and a skip / retry-forever / hard-stop miss policy.
- **Compact run HUD** — a small always-on-top status bar shows click, key, macro or
  sequence telemetry, and its STOP button halts everything.
- **Automation page** — a dedicated home for profiles and schedules, grouped under
  AUTOMATION in the sidebar.
- **Better roadmap** — the Updates page now separates SHIPPED, NEXT and EXPLORING
  milestones, with the full plan in `docs/roadmap.md`.

All v2.4.0 features are retained: rebuilt engines, Discord Rich Presence, Explore,
43 interface languages, Linux builds and GitHub-powered updates.

### Downloads

- Windows installer: `AutoClicker-Setup-2.5.0.exe`
- Linux: `AutoClicker-2.5.0-linux-x86_64.tar.gz`
- GitHub release: https://github.com/daxiKing/AutoClicker/releases/tag/v2.5.0

AutoClicker is legitimate automation only. It sends synthetic input and matches pixels
on your own screen; it does not read game memory, bypass anti-cheat, or implement
aimbots, aim assist or wallhacks.
