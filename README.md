# SCC GFX Engine

A broadcast graphics engine for St. Clair Saints streams, in the spirit of
Singular.live: build graphics from Photoshop files, cue them on **Preview**,
and **Take** them to **Program** with a cut, fade or stinger. The outputs are
see-through 1920×1080 web pages for OBS or vMix, reachable from any PC on the
network, and graphics can be exported as plain HTML.

## Install

Download **SCC-GFX-Engine-Setup.exe** from the
[latest release](https://github.com/owenbparker/GFX-Engine/releases/latest) and run it
(no admin rights needed; it installs to `C:\SCC GFX Engine`). The app updates
itself: when a new release is out, an **Update** button shows in the top bar.
The SCC HUD Manager installs and updates it too.

The first time it starts, Windows may ask whether to let it on the network:
allow it on private networks so other PCs can use the outputs.

## The pages

**Control**: Preview (green) and Program (red) monitors, the take bar, the
list of graphics and the selected graphic's fields.

- **PVW** puts a graphic on Preview (or double-click it). Type in its fields
  on the right: Preview changes as you type.
- **TAKE** (Space) puts Preview on Program with the transition picked above it
  (1–9 pick one); **CUT** (Enter) does it at once.
- **IN / OUT** takes one graphic straight on or off air with its own
  animation, leaving the rest alone.
- **Update on air** sends the fields' new values to Program without a transition.

**Composer**: make and edit graphics. Pick a graphic on the left and its layers
below it; drag on the canvas to move, handles to resize (snaps to the edges,
the middle and other layers). On the right: the layer's position, look, and
In / Out animation. Give a layer a **field** name to change it from Control.

**Assets**: everything the graphics use. Drop files anywhere on the window:

| File | What happens |
| --- | --- |
| Photoshop `.psd` | becomes a graphic: text layers stay editable text (same font, size, colour, tracking), every other layer becomes a picture in place, with a starting animation |
| `.mov` / `.avi` / `.mkv` | converted for the web: see-through video (QuickTime Animation, ProRes 4444) to WebM with alpha, the rest to MP4 |
| PNG sequence in a `.zip` | becomes one see-through WebM (frame rate set beside the Add button) |
| After Effects | export **Lottie** (`.json`, with the Bodymovin plugin) for animations that stay sharp and editable, or render a `.mov` with alpha. `.aep` files can't be played directly |
| `.ttf` / `.otf` / `.woff` | a font: text using it (by its PostScript name, as Photoshop records it) picks it up |
| pictures, `.mp4`, `.webm`, `.svg` | used as they are |
| `.csv` / `.xlsx` / `.txt` | added and made a data source |

Fonts the graphics use that aren't added yet are listed at the top; a similar
font stands in until then (Gotham → Montserrat, Trade Gothic → Barlow Condensed).

**Data**: Google Sheets (shared "Anyone with the link can view", or published
to the web), CSV / Excel / text / JSON files (added, or anywhere on the PC,
re-read when they change) and web addresses. Click a cell to copy its
reference, and use it in a field or text layer:

- `{{Match!B2}}`: cell B2 of the source called Match
- `{{Match!Team#3}}`: the "Team" column, 3rd row under the headers
- `{{Match!Score}}`: the cell next to "Score" in column A
- `{{time}}`, `{{time24}}`, `{{date}}`, `{{countdown:19:30}}`: the clock, and a countdown to 7:30 PM

**Transitions**: what TAKE can use. Cut, Fade, Dip (to a colour), Wipe,
Animate (each graphic's own In / Out) and **Stingers**: a video that plays
over everything, with Program changing underneath at the **cut point**. The
cut point is found by itself (the first frame that covers the whole screen)
and can be set by scrubbing the video.

**Outputs**: the addresses to add as Browser sources (Program, Preview, and one
per graphic), the network settings and the other engines on the network, the
HTML export, a workspace backup, and the log.

## Outputs and the network

    http://<this PC>:8782/output                Program (with transitions and stingers)
    http://<this PC>:8782/output?bus=preview    Preview
    http://<this PC>:8782/output?comp=<id>      one graphic, as it is on Program
    http://<this PC>:8782/control               the control panel, from any PC

Engines announce themselves on the network (UDP 8783) and show up under
Outputs > Engines on the network; **Scan** also looks for them directly.
Turn off "Let other PCs use this engine" to keep it to this PC.

## HTML export

Outputs > Export HTML makes a `.zip` of plain web files with the graphics,
their pictures, video and fonts, and a snapshot of the data. Open `index.html`
as a browser source, or use it as a CasparCG / SPX template:

- `?autoplay=0`: wait for `play()` (CasparCG and SPX call it)
- `?Field%20Name=Text`: set a field
- `?live=http://PC:8782`: follow that engine's Program instead
- `play()`, `stop()`, `next()`, `update(data)` (JSON, or CasparCG's XML)

## From source

    pip install pywebview pillow psd-tools openpyxl imageio-ffmpeg
    python -m gfxengine            # just the engine (open http://localhost:8782/control)
    python -m gfxengine.gui        # in its own window
    python -m unittest discover -s tests

The graphics live in `workspace/` next to the app (`project.json` and
`assets/`); a new install starts with the SCC example graphics from
`starter/` (rebuilt with `tools/make_starter.py`). Every push to `main`
builds the Windows app and publishes a release.
