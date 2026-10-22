## SCC GFX Engine

Runs the SCC GFX Engine's graphics from Companion: Preview, Program, Take and quick functions.

**Setup**

1. In the GFX Engine, open **Extras > Outputs**. The Companion box there shows the address and port to use.
2. If Companion runs on a different PC, tick **Let other PCs use this engine** there.
3. Add an **SCC GFX Engine** connection in Companion and enter that address and port.

**Presets**

- **Preview**: one button per graphic. Puts it on Preview or takes it off; green while it's on Preview.
- **Program**: one button per graphic. Takes it in or out of Program on its own, with its own animation; red while it's on air.
- **Take**: Take (with the default transition, or one per transition), Clear Program, Clear Preview, Clear all, and Update Program (sends the values edited on Preview to air without a transition).
- **Score**: each team's score +1 / -1 (the button shows the score), and reset to 0-0.
- **Quick functions**: clock mode (time, Starting Soon, BRB), timer start / pause and reset, background loop on / off, whose players the player graphics show, how many caster boxes. Lit while it's what's set.

The presets follow the workspace that's open: add, rename or open another workspace and they update. A button made from a preset keeps working in another workspace that has a graphic with the same name.

**Actions**

Preview on / off / toggle, Program in / out / toggle (any transition), Take (any transition), Clear, Update Program, Quick function.

**Feedbacks**

Graphic is on Preview, Graphic is on Program, Quick function is set (also: something is on Preview, something is on Program).

**Variables**

`workspace`, `preview`, `program`, `default_transition`, `clock`, `timer`, `best_of`, `casters`, `left_name`, `left_short`, `left_score`, `right_name`, `right_short`, `right_score`.
