# Mobile

A voice-first product is used on a phone, so the phone is the primary target
rather than a reduced desktop.

## Breakpoints

| Width | Layout |
|---|---|
| `> 900px` | Tiled panels (Dockview), side-by-side |
| `≤ 900px` | `StackedLayout`: one panel at a time, bottom tab bar |
| `≤ 640px` | Phone rules: touch targets, sticky composer, safe areas |

`useMediaQuery('(max-width: 900px)')` chooses the layout. There is one
implementation of each panel, shared by both layouts — a mobile-only fork would
drift.

## Rules

* **44×44px minimum for every control.** The previous 12.5px tab pills were
  roughly half that. `.btn`, `.stacked__tab` and the voice control are all sized
  against this.
* **`16px` minimum font size on inputs.** Under 16px, iOS Safari zooms the whole
  page when the field is focused.
* **Safe areas.** `env(safe-area-inset-*)` on the header, the composer and the
  bottom bar, with `viewport-fit=cover` in the viewport meta so the browser
  reports the insets at all.
* **Composer stays reachable.** `position: sticky` above the bottom edge, plus
  `interactive-widget=resizes-content` so the on-screen keyboard resizes the
  content box rather than covering it.
* **Navigation at the thumb.** On a phone the tab strip becomes a bottom bar
  (`order: 2`), horizontally scrollable with scroll snapping.
* **No hover-only affordances.** `@media (hover: none)` supplies an `:active`
  response instead.
* **Enter sends on a physical keyboard, not on a touch keyboard.** The on-screen
  Enter is the only way to type a newline.

## Flow

The **composer is the whole interface**: voice control, text field, attach button
and send. Everything the user does happens in one place, so nothing has to be
found in another panel.

## Known limitations

| Limitation | Detail |
|---|---|
| No visual verification | No browser automation here; the layout is covered by CSS rules and unit tests, not screenshots. |
| iOS Safari | Strictest autoplay and microphone policy; not tested on a real device. |
| Microphone requires a secure origin | Over `http://<lan-ip>` browsers refuse the microphone. Use `./solo.sh cert` for HTTPS. |
| Landscape phones | A short-viewport rule trims chrome; not verified on a device. |
