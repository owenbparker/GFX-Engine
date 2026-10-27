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
Updating only replaces the app's own files: your workspaces (graphics, their
text and the Upcoming Schedule), the team library and settings stay as they are.

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

**Assets** (under **Extras**, with Data, Transitions and Outputs): everything the graphics use. Drop files anywhere on the window:

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
- `{{timer}}`: the timer, run from Control (Start / Pause, Reset, the time it starts from, up or down)

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
  `{{Sponsors}}` (the one on air) or `{{Sponsors all}}` (every sponsor in a
  row, as on the bottom bar of Team stats, Player stats and the Replay
  overlay). In that row, logos are shown white unless the sponsor's
  "White in footer rows" box is unticked (the SCC Alumni crest stays in
  colour). The SCC pack comes with Alienware, SCC Alumni, Tim Hortons, SRC,
  Subway, Intel, Prefire and Pulsar.
- The background loop plays behind the full-screen boards (schedule, stats,
  brackets). Turn it off, pick its colour, brightness and speed, or drop in
  another video.

The **caster lower third** shows 1 to 4 caster boxes side by side along the
bottom (picked in its Control fields, with each caster's name and handle),
in a primary colour (the box) and a secondary colour (the text, the box's
edge and its shadow), also set there.

The **ticker** has the lines every ticker scrolls (`{{Global!Ticker}}`), kept
apart by a yellow bar (a scrolling text layer's Divider colour in Composer).

The **Teams** tab has the team list (shared by every workspace, kept in
`library/teams.csv`): each team's name, short name, game, logo and colour,
and its roster: each player's headshot, name, in-game ID and country (its
flag comes with the engine). The **In-game ID** is the player's name in the
game, exactly (a "#tag" and capitals aside): it's the only thing that links
the game's stats to the player. Their **Player name** is just how graphics
show them (Team stats, Player stats, player graphics). A game HUD can fill
in the in-game IDs: League HUD's Players & Teams > Players has **Save IGN to
player** next to each player in the game, with "linked" or "unlinked". The game is picked from the games the engine
has a HUD for (League of Legends, VALORANT, Rocket League, Call of Duty, Super Smash Bros. Ultimate). One
school can have a team in several games; the list filters by game. Pick a team to edit it, drop its logo or a
player's headshot on it, or make it the left or right team. Import or export
it as a CSV (Name, Short name, Logo, Colour, Game, Player 1, Player 1 ID,
Player 1 country, Player 1 headshot, Player 2...). In Global, each side can
pick its team from the list, or save its team to it.

The **player graphics** (1 to 5 players) show the left or right team's roster
(chosen in their Control fields): each player's headshot over their name
(or in-game ID), with their flag before it. Headshots are trimmed
to the player when they're added (see-through margins cut off, and those
added before are trimmed when the engine starts), so every player fills
their spot the same way. While the roster has no
headshots, the design's own photo shows. In graphics: `{{Roster!Player 1}}`,
`{{Roster!Player 1 flag}}`, `{{Roster!Player 1 headshot}}`,
`{{Roster!Player 1 ID}}`, `{{Roster!Team}}`... They play over the
background loop, like the full-screen boards. The tournament's team boxes suggest names from it,
and the brackets show each team's logo.

The **Tournament** tab fills in the bracket graphics: the knockout bracket (8 or
16 teams: the Top 8 bracket graphic redraws itself for 16, and its Control
fields have the choice) and four groups played GSL style (two opening
matches, winners', elimination and decider). Enter the teams and the scores,
and the winners go through by themselves; the final four shows the
knockout's last two rounds. In graphics: `{{Tournament!Top R1 M1 team 1}}`,
`{{Tournament!Top champion}}`, `{{Tournament!Group A 1st}}`...

Its **Standings** section fills in the Standings (8 teams) and Standings (16
teams) graphics: each row's team (picked from the team list, or typed), its
wins, losses, points and map difference, and what the box shows (the record,
wins, losses, points, win % or map difference, and a second box if wanted;
Control has the same choice). Drop a logo on a row for that team, or drop a
batch of logos named after their teams to fill the empty rows; logos go in
the team list. Sort by record puts the most wins first. In graphics:
`{{Standings!Team 1}}`, `{{Standings!Team 1 logo}}`, `{{Standings!Team 1 stat 1}}`...

The **Upcoming Schedule** tab has the matches the Schedule graphic lists:
each one's tournament, game, match type, teams, date and time. The graphic
shows the first 1, 2 or 3 of them (chosen in that tab, or in the Schedule's
Control fields). In graphics: `{{Schedule!Match 1 tournament}}`,
`{{Schedule!Match 1 game}}`, `{{Schedule!Match 1 teams}}`,
`{{Schedule!Match 1 when}}`; a layer whose Show is `{{Schedule!Match 2 show}}`
is only on screen while the second match is. The Schedule's score bar shows
each team's logo in front of its name.

The Schedule's and the scorebug's **clock** has two lines: the time, and under it in yellow what
it is. Its Control fields choose Current time (the time of day, LOCAL TIME),
Starting Soon or Be Right Back (a countdown to the time picked, with STARTING
SOON or BE RIGHT BACK under it). The scorebug's clock is the same one, so
changing it in either graphic's fields changes both. In graphics: `{{clock}}` and
`{{Global!Clock label}}`.

The **Timer bug** (rebuilt from the vMix Timer Bug title) shows HIGHLIGHTS
(its Title field) over the timer. Its Control fields start and pause the
timer, reset it, set the time it starts from (m:ss) and whether it counts up
or down (a countdown stops at 00:00). It's one timer for every graphic with
`{{timer}}`, on air too; Companion has Timer start / pause and Timer reset.

The SCC graphics in a workspace are brought up to date when the engine has
newer versions of them, unless you've changed them in Composer.

## Game HUDs

The League, VALORANT, CoD and Rocket League HUDs have a **GFX Engine** page:
scan the network, connect, and the HUD sends its live stats (a data table
named after it, e.g. `{{League HUD!KILLS LEFT}}`) and the series score (into
Global) about once a second. **Use Global Information** takes the teams'
names, short names and logos, and the sponsors (their logos, in order, and
seconds each) from here into the HUD (CoD HUD: the teams only; it has no
sponsor spot). Each HUD's Players & Teams page also has **Players**: each
player in the game, linked or unlinked to their team's roster here, with
**Save IGN to player** (CoD HUD: none, it doesn't read player names). The HUD side is in
`hud-link/` (copied into each HUD).

A HUD can also offer its own pages: the VALORANT HUD's agent select, in-game
HUD and scoreboard. Each shows up in Control's graphics under **Game HUD**
(added once, the first time; delete one and it stays gone), live from the
HUD, to take on air like any other graphic. A HUD on another PC needs "Let
other PCs on the network read the HUD" ticked in it.

The players' stats from whichever HUD is connected also go into one table,
`Stats`, the same for every game: `{{Stats!Left player 1}}`,
`{{Stats!Left player 1 stat 1}}`, `{{Stats!Stat 1 title}}` (KILLS, GOALS...),
`{{Stats!MVP}}`, `{{Stats!Status}}` (LIVE or FINAL). The team stats, player
stats and player graphics use it. The last game's stats are kept after it
ends (and over a restart) until the next game starts or you press **Clear
stats** in Global.

Each game has its own columns on **Team stats** and rows on **Player stats**:
League of Legends shows K/D/A, CS and DMG (and GOLD on Player stats), VALORANT
ACS, kills and deaths (and assists on Player stats), Rocket League goals,
saves and score. The big numbers at the top of Team stats are each team's
kills in League, rounds won in VALORANT and goals in Rocket League:
`{{Stats!Left kills}}` (`{{Stats!Left total kills}}` is always the kills).
VALORANT's ACS is an estimate: the spectator screen the HUD reads has no
damage or ACS, so each kill counts about 200 and each assist 25, over the
rounds played. The top player on Player stats is the one with the most of
its first row (ACS in VALORANT). League's damage only comes once the game is
over, from the League client's end-of-game stats on the HUD's PC (Riot's live
game API doesn't report it); until then DMG shows a dash. Gold is the HUD's
estimate during the game and exact after it.

The **Player stats** page shows one player from the game: the one with the
most of the first stat (kills, goals) unless another is picked in its
Control fields (every player in the game is listed). Their name, flag and
headshot come from their team's roster in the Teams tab, matched by in-game
ID: `{{Stats!MVP name}}`, `{{Stats!MVP flag}}`, `{{Stats!MVP headshot}}`,
`{{Stats!MVP row 1}}` (and `{{Stats!Row 1 title}}`)...

Team stats (a picture left of each player) and Player stats show each
team's players as their **headshots** (from the Teams tab) or the
**champions** (League) or **agents** (VALORANT) they're playing, picked per
team in each page's own Control fields ("Player pictures": Left team, Right
team; Team stats and Player stats are set separately). On Team stats a
headshot shows only its top third (the face); on Player stats the headshot
is full size (it can rise above the top of the box) and the champion's
square art fills the box, uncropped. `{{Stats!Left player 1 headshot}}`,
`{{Stats!Left player 1 champion}}`, `{{Stats!MVP champion}}`.

## Outputs and the network

    http://<this PC>:8782/output                Program (with transitions and stingers)
    http://<this PC>:8782/output?bus=preview    Preview
    http://<this PC>:8782/output?comp=<id>      one graphic, always (while switched on)
    http://<this PC>:8782/control               the control panel, from any PC

Each graphic's own output is switched on and off in Outputs. On, it always
shows its graphic, whether it's on Program or not (with its Program values,
or else its Preview ones); off, it shows nothing, so a browser source you
aren't using costs the PC nothing.

The outputs are made to keep up on a busy show: the engine works out what
changed once for every output and sends each only that (a take is a few
hundred bytes, not the whole project), and an output keeps every picture its
graphics use loaded and decoded ahead, so a graphic plays in only once it's
all there, never half drawn. That costs some memory (a few hundred MB with
many graphics), on purpose.

Engines announce themselves on the network (UDP 8783) and show up under
Outputs > Engines on the network; **Scan** also looks for them directly.
Turn off "Let other PCs use this engine" to keep it to this PC. **Other PCs
reach it on** picks one network (this PC's address on it: an NDI VLAN, say):
the engine then listens only there and on this PC, announces itself and scans
only there, and the Outputs list only that address. If the PC isn't on that
network, only this PC can use the engine until it is.

## Bitfocus Companion (Stream Deck)

Each release has `SCC-GFX-Companion-module.tgz`, a module for Bitfocus
Companion (import it on Companion's **Modules** page). Add an **SCC GFX
Engine** connection with this PC's address and port 8782 (Outputs shows them;
from another PC the engine needs "Let other PCs use this engine" on). Its
presets have a Preview and a Program button for every graphic in the open
workspace (green on Preview, red on air), Take (with each transition), Clear,
Update Program, and quick functions: the score, the clock mode, the
background loop, whose players the player graphics show and the caster
boxes. The module is in `companion-module/`; the engine side is
`gfxengine/companion.py` (`GET` / `POST /api/companion`).

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
`starter/` (rebuilt with `tools/make_starter.py`). The Title screen,
Starting soon, Team graphic and Sponsor footer were taken out of the pack:
a workspace drops them on its next open, unless they were edited there.
Every push to `main`
builds the Windows app and publishes a release.
