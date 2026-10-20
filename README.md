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
- **TAKE** (Space) puts what's on Preview on Program with the transition
  picked above it (1–9 pick one), and clears Preview; **CUT** (Enter) does it at once.
- **IN / OUT** takes one graphic straight on or off air with its own
  animation, leaving the rest alone.
- Graphics are listed as **full-page boards**, **lower thirds** and
  **overlays** (Composer sets which). One board and one lower third can be on
  air at a time, together: taking another board replaces the board, another
  lower third replaces the lower third, and overlays (scorebug, replay) stay.
- **Update on air** sends the fields' new values to Program without a transition.

**Composer**: make and edit graphics. Pick a graphic on the left and its layers
below it; drag on the canvas to move, handles to resize (snaps to the edges,
the middle and other layers). On the right: the layer's position, look, and
In / Out animation. Give a layer a **field** name to change it from Control.
**★** adds a special element that follows Global: the left or right team's
logo, name, short name, score or colour, the tournament logo, the sponsors,
the ticker, the background loop or the knockout bracket.

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

## Workspaces

The app opens on **Home**: your workspaces, one per event or show, each with
its own graphics, files, data, transitions and global configuration. **+ New
workspace** asks for a name and a picture, and starts from the SCC graphics
or empty. Fonts are shared by every workspace (`library/fonts`), and are
matched by any of their names, so a PSD that records "Carbon-Bold" finds the
file whose font is called "Carbon-Black". Workspaces live in `workspaces/`
next to the app.

## Global configuration

The **Global** tab holds the event's basics: both teams (name, short name,
logo, colour, score), best of, game, event, stage, and any fields you add.
Every graphic can use them as `{{Global!Left name}}`, `{{Global!Right logo}}`,
`{{Global!Left score}}`...; picture fields in Control list the team logos,
and every field's ⛓ menu links it to one.

It also has the **tournament logo**, the **sponsors** and the **background
loop**, which every SCC graphic uses, so changing them here changes them all:

- The team logos and tournament logo fill every logo spot (the design's own
  picture shows while there's none).
- Sponsors rotate in every sponsor spot, each for the seconds you give it,
  with a lift-and-fade between them. All spots show the same sponsor at the
  same time; the list shows which one is on air and how long it has left, and
  a sponsor layer can show that as a bar too (Composer: "Show a bar with the
  time it has left"). In Composer, a picture layer's source can be
  `{{Sponsors}}`.
- The background loop plays behind the full-screen boards (schedule, stats,
  brackets). Turn it off, pick its colour, brightness and speed, or drop in
  another video.

The **ticker** has the lines every ticker scrolls (`{{Global!Ticker}}`), kept
apart by a yellow bar (a scrolling text layer's Divider colour in Composer).

The **Teams** tab has the team list (shared by every workspace, kept in
`library/teams.csv`): each team's name, short name, game, logo and colour,
and its roster: each player's headshot, name, in-game ID and country (its
flag comes with the engine). One school can have a team in several games;
the list filters by game. Pick a team to edit it, drop its logo or a
player's headshot on it, or make it the left or right team. Import or export
it as a CSV (Name, Short name, Logo, Colour, Game, Player 1, Player 1 ID,
Player 1 country, Player 1 headshot, Player 2...). In Global, each side can
pick its team from the list, or save its team to it.

The **player graphics** (1 to 5 players) show the left or right team's roster
(chosen in their Control fields): each player's headshot over their name
(or in-game ID), with their flag before it. While the roster has no
headshots, the design's own photo shows. In graphics: `{{Roster!Player 1}}`,
`{{Roster!Player 1 flag}}`, `{{Roster!Player 1 headshot}}`,
`{{Roster!Player 1 ID}}`, `{{Roster!Team}}`... The tournament's team boxes suggest names from it,
and the brackets show each team's logo.

The **Tournament** tab fills in the bracket graphics: the knockout bracket (8 or
16 teams: the Top 8 bracket graphic redraws itself for 16, and its Control
fields have the choice) and four groups played GSL style (two opening
matches, winners', elimination and decider). Enter the teams and the scores,
and the winners go through by themselves; the final four shows the
knockout's last two rounds. In graphics: `{{Tournament!Top R1 M1 team 1}}`,
`{{Tournament!Top champion}}`, `{{Tournament!Group A 1st}}`...

The **Upcoming Schedule** tab has the matches the Schedule graphic lists:
each one's tournament, game, match type, teams, date and time. The graphic
shows the first 1, 2 or 3 of them (chosen in that tab, or in the Schedule's
Control fields). In graphics: `{{Schedule!Match 1 tournament}}`,
`{{Schedule!Match 1 game}}`, `{{Schedule!Match 1 teams}}`,
`{{Schedule!Match 1 when}}`; a layer whose Show is `{{Schedule!Match 2 show}}`
is only on screen while the second match is. The Schedule's score bar shows
each team's logo in front of its name.

The Schedule's **clock** has two lines: the time, and under it in yellow what
it is. Its Control fields choose Current time (the time of day, LOCAL TIME),
Starting Soon or Be Right Back (a countdown to the time picked, with STARTING
SOON or BE RIGHT BACK under it). In graphics: `{{clock}}` and
`{{Global!Clock label}}`.

The SCC graphics in a workspace are brought up to date when the engine has
newer versions of them, unless you've changed them in Composer.

## Game HUDs

The League, VALORANT, CoD and Rocket League HUDs have a **GFX Engine** page:
scan the network, connect, and the HUD sends its live stats (a data table
named after it, e.g. `{{League HUD!KILLS LEFT}}`) and the series score (into
Global) about once a second. **Use Global Information** takes the teams'
names, short names and logos from here into the HUD. The HUD side is in
`hud-link/` (copied into each HUD).

The players' stats from whichever HUD is connected also go into one table,
`Stats`, the same for every game: `{{Stats!Left player 1}}`,
`{{Stats!Left player 1 stat 1}}`, `{{Stats!Stat 1 title}}` (KILLS, GOALS...),
`{{Stats!MVP}}`, `{{Stats!Status}}` (LIVE or FINAL). The team stats, player
stats and player graphics use it. The last game's stats are kept after it
ends (and over a restart) until the next game starts or you press **Clear
stats** in Global.

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
