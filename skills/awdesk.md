---
name: awdesk
description: >-
  Put the agent on someone's desk: install the Aither desktop companion from its
  release assets, keep it talking to a daemon, and use decision cards as the
  place a question actually reaches a person instead of scrolling past in a
  transcript. Use when an agent needs a human answer at the right moment, when a
  tray/avatar surface should show what the agent is doing, or when someone asks to
  "put it on my desktop".
---

# awdesk — the agent on your desk

awdesk is a tray app: an icon, an avatar, and a **decision card** that pops when
the agent needs a person. That last part is the reason it exists. A question that
lands as a card gets answered; a question buried in a long transcript does not.

It is a client. It shows and asks; the work happens behind the daemon it talks to.

Source: <https://github.com/Aitherium/awdesk>

## Install

Download the asset for the platform from the
[releases page](https://github.com/Aitherium/awdesk/releases), and check the
download against `SHA256SUMS.txt` in the same release.

From source:

```bash
git clone https://github.com/Aitherium/awdesk
cd awdesk
npm install && npx electron .
```

## Use it for what it is good at

- **Approval cards.** Anything that changes state and needs a yes goes here, not
  into a chat window.
- **Presence.** A tray icon tells a person something is running, without them
  reading a log.
- **Hand-off.** When the agent is stuck on a judgement call, the card is the
  hand-off point.

## Traps

- **An empty desk is usually a missing daemon.** Check what it should be talking
  to before reinstalling.
- **One install at a time.** A source build running alongside an installed copy
  gives two tray icons and two bridges, and it is rarely obvious which one
  answered.
- **Signing varies by channel.** Verify the hash rather than clicking through an
  installer warning.
- **Do not put a decision card behind another window** and call the agent
  unresponsive. The card has to be able to reach the front.

## What it does not do

It serves no tools. If you need a capability, it lives in the daemon — awdesk is
how a person sees and answers.

## Windows / WSL2 Launch & Health Verification

- **Never leave a stale Electron tree running**: Before declaring `awdesk` fixed or restarted, stop existing `D:\desk` `electron.exe` processes and verify the final count is lean (~5 Electron processes for one instance, never 12+).
- **Launch into interactive Session 1 from WSL2**: Do not launch `electron.exe` directly from a WSL2 subshell. Use `Shell.Application` COM `ShellExecute` on the installed startup launcher (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\aither-awdesk.vbs`) so windows, tray, and fairies attach to the desktop session.
- **Live health gate (`http://127.0.0.1:47931/health`)**: Confirm all four before reporting ready:
  1. HTTP `200` with `"ok": true` within ~5–10s.
  2. `stage.present.mode === "gpu"` (if stuck on software rendering or high GPU CPU, check for a stale Windows `DirectX\UserGpuPreferences` `GpuPreference=1` pin on `electron.exe`).
  3. `stage.mainLag.maxMs` stays low (`< 100ms` at steady state; multi-second spikes mean a synchronous disk/process scan crept onto the main thread).
  4. Main Electron process runs at `Normal` priority (not `AboveNormal`), and child helper pipes attach `error` listeners so `EPIPE` never opens a blocking modal error dialog that triggers `hang-watchdog`.

## Desk Card UX Invariants (Never Regress)

- **Draggable without DPI blow-up**: Whisper cards (`orb-window.cjs`) stay `movable: true` with left-drag on `#n-head` + middle-drag anywhere via `applyWindowDrag()` using `screen.getCursorScreenPoint()` + `win.setBounds(next, false)` (never raw `setPosition()` on Windows fractional DPI). Disable Three.js `OrbitControls` middle-button `MOUSE.DOLLY` (`MIDDLE: undefined`) and suppress middle-drag pointer/wheel bleed.
- **Selectable & actionable**: Keep `user-select: text` across whisper cards (`orb.html`) and Deck/Inbox cards (`styles.css`). Surface direct clickable links (`cardLinks` — GitHub issues/PRs/URLs) on collapsed whisper cards and keep 1-click **Copy**, **Send to agent**, and **Terminal** buttons working on both surfaces.

## Virtual Phone & Phone-to-PC Pairing Doctrine

- **Zero Developer Options / zero ADB / zero mDNS by default**: Never make USB debugging, Wireless ADB, or mDNS multicast the default phone pairing UX — mDNS dies whenever PC Ethernet sits behind a firewall and the phone is on Wi-Fi.
- **Aither-native transport**: Bind `phone-link.cjs` on `0.0.0.0:47938` (LAN + Tailscale + Cloudflare Tunnel fallback), pair via 1-scan `aither://pair?...` QR (`POST /link/pair-qr` with Ed25519 `X-Aither-Device-Hello` + single-use 5-min code), and stream H.264 + touch/notifications over `/link/screen` WebSocket (`phone-stream.cjs`). Keep USB/Wireless ADB collapsed under an optional **Advanced** drawer.
- **Verify QR encoders with a real decoder**: Whenever changing `phone-qr.cjs`, verify every supported QR version (V2–V9, including ISO/IEC 18004 Rule 3 finder-pattern penalty) against OpenCV `cv2.QRCodeDetector` for exact byte-for-byte decode.

## Windows-Native `D:\desk` Build & Test Commands

- Run `npm.cmd run build` and `node.exe --test` natively on Windows via `/var/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command '...' < /dev/null` (not WSL2 Linux `node` over 9p).
- After `node.exe scripts\restart-desk.cjs` prints `desk up (main <pid>)`, Electron inherits PowerShell's stdout handle — cancel the PowerShell wrapper once `http://127.0.0.1:47931/health` returns `ok: true` (Electron stays running in Session 1).
