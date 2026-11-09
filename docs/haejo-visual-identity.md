# Haejo visual identity

**Mark.** The Hangul initial **ㅎ**, the first letter of 해줘 ("do it for me"). The coral
dot is the ask, and 해, the sun. The bar is the blank you fill in ("Ask Haejo to ____")
and the Flow the agent records. The ring is the result, checked and closed. In motion the
sun rises from behind the bar when a task starts and the ring closes when the result is
checked. This replaced the pointer *t* of Tacto on 2026-11-09, when the product was renamed.
Rationale, explorations and application mockups: [brand book](haejo-brandbook.html).

The mark and wordmarks are original drawings made for this project. They do not imply
trademark clearance or any affiliation with other products named Haejo.

## Assets

| Use | Path |
|---|---|
| Standalone mark (transparent) | `docs/assets/haejo-logo.svg`, `sites/haejo/dist/assets/haejo-logo.svg` |
| Mark + wordmark (horizontal lockup) | `docs/assets/haejo-wordmark.svg`, `sites/haejo/dist/assets/haejo-wordmark.svg` |
| Hangul, stacked and ivory lockups, wordmarks alone | `docs/assets/brand/haejo/haejo-lockup*.svg`, `haejo-word.svg`, `haejo-hangul.svg` |
| README banner / social card | `docs/assets/haejo-banner.svg`, `docs/assets/brand/haejo/haejo-social.svg` (1200×630) |
| Favicon (ink tile, like the app icon) | `sites/haejo/dist/assets/favicon.svg` |
| macOS app icon | `docs/assets/haejo-app.icns`, sources `docs/assets/haejo-app-icon.svg`, `docs/assets/haejo-app-icon-small.svg` |
| Menu-bar state templates (proposal, not wired) | `docs/assets/brand/haejo/haejo-state-{idle,working,done,attention}.svg` |
| Working animation (SMIL) | `docs/assets/brand/haejo/haejo-working.svg` |

`setup/build_brand_assets.py` writes every SVG and the app icon from one set of constants;
`--check` fails if a tracked copy has drifted. All files are self-contained SVG: no fonts,
scripts, links, raster data or external references. Wordmark letters are drawn as paths.
Only the banner and social card use live text, set in the system sans stack.

## Palette

| Role | Hex | Notes |
|---|---|---|
| Ink | `#1b211c` | Mark strokes and text. On dark backgrounds use ivory `#f6f4ed`. |
| Sun | `#fa6b3b` | The sun dot and the j's dot only. Not for small text. |
| Sun text | `#c4532c` | Display text on ivory (e.g. "use your apps."). |
| Ivory | `#f6f4ed` | Background; the mark on ink tiles (app icon, favicon). |
| Moss | `#5f6b58` | Secondary text, idle state. |
| Pine / Amber / Brick | `#2f7a55` / `#b9800f` / `#a8322a` | Done / needs you / failed status chips. Not brand accents. |

## Construction and spacing

- 32-unit grid. Stroke 4.0 with flat bar ends; ring and dot are true circles.
- Bar 27 wide, ring outer diameter 17.4: the bar is about 1.55× the ring, as in a
  well-drawn ㅎ, so the mark fills the square sideways.
- The dot is drawn at 0.72× the ring's counter so it *looks* the same size as the hole
  (a filled disc looks larger than an equal opening).
- Latin `haejo`: geometric grotesk, x-height 16, stroke 4.0, flat terminals, optical pair
  spacing (h·a 2.0, a·e 1.9, e·j 1.5, j·o 2.1). In the lockup the baseline meets the ring's bottom.
- Hangul `해줘`: same stroke and terminals; its ㅎ follows the mark's rules.
- Clear space: at least the ring's diameter on every side.
- Never attach the dot to the bar, enlarge it, recolor the strokes coral, rotate the mark,
  or hyphenate the name (`HAE-JO`).

## Minimum sizes

- Mark: 16 px. At 16–32 px use the small optical size (stroke 4.6) from
  `haejo-app-icon-small.svg`; prefer the ink tile on busy surfaces.
- Horizontal lockup: 96 px wide on screen, 24 mm in print. Below that, use the mark alone.

## Product and interface icons

Claude and Codex are identified with unmodified official raster assets served
locally, not font glyphs or approximations. They identify compatible products;
Haejo is independent and does not claim sponsorship or endorsement. These
third-party marks remain the property of their respective owners and are not
covered by the Haejo artwork description above.

Retrieved 2026-10-15:

| Local asset | Official source | Context |
|---|---|---|
| `sites/haejo/dist/assets/claude-icon.png` | [Claude homepage](https://claude.com/) · [original asset](https://assets.claude.com/95a868946ac8a31e5ff832e2899f294aa368b836.png) | Homepage favicon; 32 × 32 |
| `sites/haejo/dist/assets/codex-icon.png` | [Codex extension published by OpenAI](https://marketplace.visualstudio.com/items?itemName=openai.chatgpt) · [original asset](https://openai.gallerycdn.vsassets.io/extensions/openai/chatgpt/26.51007.21434/1791508178385/Microsoft.VisualStudio.Services.Icons.Default) | Official extension icon (OpenAI Blossom); 400 × 400 |

The Codex entry deliberately uses the icon shipped by OpenAI with its Codex
extension. It is the OpenAI Blossom, not an invented Codex-specific symbol.
See [OpenAI's brand guidelines](https://openai.com/brand/).

`sites/haejo/dist/assets/ui-icons.svg` contains project-authored vector symbols
for arrows, check, repeat, zero, swap, disclosure, stop, workflow and code file.
The same symbols serve static HTML and dynamic demo rows. Decorative icons are
hidden from assistive technology; adjacent labels provide the accessible name.
Textual workflow arrows and the calculator multiplication sign remain text.

Asset checksums (SHA-256):

- `claude-icon.png`: `4004381309500f25e49a1ae639912ce307ea81da74cc383954a1ac8b9d343fe6`
- `codex-icon.png`: `2ce1c57dd3b312417106a487815ab1235bddce17e1fa9b32a2f048bd71ee25d3`
