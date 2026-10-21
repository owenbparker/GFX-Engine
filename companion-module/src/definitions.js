// What the GFX Engine can be told to do (mirrors gfxengine/companion.py).
// The graphics and transitions come from the engine (they're the workspace's).

const QUICK = {
	score_left_up: 'Score: left team +1',
	score_left_down: 'Score: left team -1',
	score_right_up: 'Score: right team +1',
	score_right_down: 'Score: right team -1',
	score_reset: 'Score: reset to 0-0',
	clock_time: 'Clock: local time',
	clock_soon: 'Clock: Starting Soon countdown',
	clock_brb: 'Clock: Be Right Back countdown',
	bgloop: 'Background loop: on / off',
	roster_left: 'Player graphics: left team',
	roster_right: 'Player graphics: right team',
	caster_1: 'Casters: 1 box',
	caster_2: 'Casters: 2 boxes',
	caster_3: 'Casters: 3 boxes',
	caster_4: 'Casters: 4 boxes',
}

// On/off states that can only be read (feedbacks), not run.
const STATES = {
	preview_any: 'Something is on Preview',
	program_any: 'Something is on Program',
}

// Quick functions that light their button while they're what's set.
const LIT = ['clock_time', 'clock_soon', 'clock_brb', 'bgloop', 'roster_left', 'roster_right', 'caster_1', 'caster_2', 'caster_3', 'caster_4']

const VARIABLES = {
	workspace: 'Workspace open',
	preview: 'Graphics on Preview',
	program: 'Graphics on Program',
	default_transition: 'Default transition (Take)',
	clock: 'Clock mode',
	best_of: 'Best of',
	casters: 'Caster boxes',
	left_name: 'Left team name',
	left_short: 'Left team short name',
	left_score: 'Left team score',
	right_name: 'Right team name',
	right_short: 'Right team short name',
	right_score: 'Right team score',
}

const choices = (obj) => Object.entries(obj).map(([id, label]) => ({ id, label }))

module.exports = { QUICK, STATES, LIT, VARIABLES, choices }
