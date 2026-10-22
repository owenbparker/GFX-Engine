// Bitfocus Companion module for the SCC GFX Engine.
//
// It polls the engine's GET /api/companion a few times a second (for the
// feedbacks, the variables and the workspace's graphics) and sends actions to
// POST /api/companion. See gfxengine/companion.py in the engine.

const { InstanceBase, Regex, runEntrypoint, InstanceStatus, combineRgb } = require('@companion-module/base')
const { QUICK, STATES, LIT, VARIABLES, choices } = require('./definitions')

const GREEN = combineRgb(0, 178, 72)
const RED = combineRgb(214, 32, 32)
const AMBER = combineRgb(245, 197, 24)
const DARK = combineRgb(20, 22, 25)
const WHITE = combineRgb(255, 255, 255)
const BLACK = combineRgb(0, 0, 0)

const MODES = [
	{ id: 'toggle', label: 'Toggle' },
	{ id: 'on', label: 'On' },
	{ id: 'off', label: 'Off' },
]

class GfxEngineInstance extends InstanceBase {
	async init(config) {
		this.config = config
		this.data = null
		this.failed = null // not known yet
		this.signature = null
		this.define()
		this.setVariableDefinitions(Object.entries(VARIABLES).map(([variableId, name]) => ({ variableId, name })))
		this.startPolling()
	}

	async destroy() {
		clearTimeout(this.timer)
		this.stopped = true
	}

	async configUpdated(config) {
		this.config = config
		this.startPolling()
	}

	getConfigFields() {
		return [
			{
				type: 'static-text',
				id: 'info',
				width: 12,
				label: '',
				value:
					"Enter the address of the PC the GFX Engine runs on (127.0.0.1 if it's this PC). The engine's Extras > Outputs page shows it. From another PC, the engine needs 'Let other PCs use this engine' on.",
			},
			{ type: 'textinput', id: 'host', label: 'GFX Engine PC address', width: 8, default: '127.0.0.1', regex: Regex.HOSTNAME },
			{ type: 'textinput', id: 'port', label: 'Port', width: 4, default: '8782', regex: Regex.PORT },
			{ type: 'number', id: 'poll', label: 'Check every (ms)', width: 4, default: 250, min: 100, max: 5000 },
		]
	}

	base() {
		return `http://${(this.config.host || '127.0.0.1').trim()}:${Number(this.config.port) || 8782}`
	}

	// --- talking to the engine -------------------------------------------

	startPolling() {
		clearTimeout(this.timer)
		this.updateStatus(InstanceStatus.Connecting)
		const tick = async () => {
			if (this.stopped) return
			await this.refresh()
			this.timer = setTimeout(tick, Math.max(100, Number(this.config.poll) || 250))
		}
		tick()
	}

	async refresh() {
		try {
			const r = await fetch(this.base() + '/api/companion', { signal: AbortSignal.timeout(2000) })
			if (!r.ok) throw new Error(`HTTP ${r.status}`)
			this.apply(await r.json())
			if (this.failed !== false) this.updateStatus(InstanceStatus.Ok)
			this.failed = false
		} catch (e) {
			if (!this.failed) {
				this.log('warn', `Can't reach the GFX Engine at ${this.base()}: ${e.message}`)
				this.updateStatus(InstanceStatus.ConnectionFailure, e.message)
			}
			this.failed = true
		}
	}

	apply(data) {
		this.data = data
		// New graphics or transitions (another workspace, a graphic added or renamed): new dropdowns and presets.
		const signature = JSON.stringify([
			(data.graphics || []).map((g) => [g.id, g.name, g.kind]),
			(data.transitions || []).map((t) => [t.id, t.name]),
		])
		if (signature !== this.signature) {
			this.signature = signature
			this.define()
		}
		this.setVariableValues(data.variables || {})
		this.checkFeedbacks('on_preview', 'on_program', 'state_on')
	}

	async send(body) {
		try {
			const r = await fetch(this.base() + '/api/companion', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
				signal: AbortSignal.timeout(5000),
			})
			const data = await r.json()
			if (!r.ok || data.error) throw new Error(data.error || `HTTP ${r.status}`)
			this.apply(data)
		} catch (e) {
			this.log('error', `GFX Engine: ${e.message}`)
		}
	}

	// --- definitions -----------------------------------------------------

	graphics() {
		return (this.data && this.data.graphics) || []
	}

	graphicOption() {
		const list = this.graphics()
		return {
			type: 'dropdown',
			id: 'graphic',
			label: 'Graphic (or type its name)',
			default: list.length ? list[0].id : '',
			allowCustom: true,
			choices: list.map((g) => ({ id: g.id, label: `${g.name} (${g.kind})` })),
		}
	}

	transitionOption(first) {
		const list = (this.data && this.data.transitions) || []
		return {
			type: 'dropdown',
			id: 'transition',
			label: 'Transition',
			default: '',
			choices: [{ id: '', label: first }, ...list.map((t) => ({ id: t.id, label: t.name }))],
		}
	}

	define() {
		this.setActionDefinitions(this.actions())
		this.setFeedbackDefinitions(this.feedbacks())
		this.setPresetDefinitions(this.presets())
	}

	actions() {
		return {
			preview: {
				name: 'Preview: put a graphic on / off Preview',
				options: [this.graphicOption(), { type: 'dropdown', id: 'mode', label: 'Do', default: 'toggle', choices: MODES }],
				callback: (e) => this.send({ action: 'preview', id: e.options.graphic, mode: e.options.mode }),
			},
			program: {
				name: 'Program: take a graphic in / out on its own',
				options: [
					this.graphicOption(),
					{ type: 'dropdown', id: 'mode', label: 'Do', default: 'toggle', choices: MODES },
					this.transitionOption("The graphic's own animation"),
				],
				callback: (e) =>
					this.send({ action: 'program', id: e.options.graphic, mode: e.options.mode, transition: e.options.transition }),
			},
			take: {
				name: 'Take: Preview to Program',
				options: [this.transitionOption('The default transition')],
				callback: (e) => this.send({ action: 'take', transition: e.options.transition }),
			},
			clear: {
				name: 'Clear Program / Preview',
				options: [
					{
						type: 'dropdown',
						id: 'bus',
						label: 'Clear',
						default: 'program',
						choices: [
							{ id: 'program', label: 'Program' },
							{ id: 'preview', label: 'Preview' },
							{ id: 'both', label: 'Both' },
						],
					},
					this.transitionOption("Each graphic's own animation"),
				],
				callback: (e) => this.send({ action: 'clear', bus: e.options.bus, transition: e.options.transition }),
			},
			send: {
				name: 'Update Program: send the Preview values to air (no transition)',
				options: [{ ...this.graphicOption(), label: 'Graphic (empty = everything on Program)', default: '' }],
				callback: (e) => this.send({ action: 'send', id: e.options.graphic }),
			},
			quick: {
				name: 'Quick function',
				options: [{ type: 'dropdown', id: 'quick', label: 'Do', default: 'score_left_up', choices: choices(QUICK) }],
				callback: (e) => this.send({ action: 'run', id: e.options.quick }),
			},
		}
	}

	feedbacks() {
		const onBus = (bus) => (fb) => {
			const key = String(fb.options.graphic || '').trim().toLowerCase()
			const g = this.graphics().find((g) => g.id === fb.options.graphic) || this.graphics().find((g) => g.name.toLowerCase() === key)
			return !!(g && g[bus])
		}
		return {
			on_preview: {
				type: 'boolean',
				name: 'Graphic is on Preview',
				description: 'Lights the button green while the graphic is on Preview',
				defaultStyle: { bgcolor: GREEN, color: WHITE },
				options: [this.graphicOption()],
				callback: onBus('preview'),
			},
			on_program: {
				type: 'boolean',
				name: 'Graphic is on Program (on air)',
				description: 'Lights the button red while the graphic is on air',
				defaultStyle: { bgcolor: RED, color: WHITE },
				options: [this.graphicOption()],
				callback: onBus('program'),
			},
			state_on: {
				type: 'boolean',
				name: 'Quick function is set / something is on a bus',
				description: 'Lights the button while it is what is set (clock mode, background loop, roster side, casters)',
				defaultStyle: { bgcolor: AMBER, color: BLACK },
				options: [
					{
						type: 'dropdown',
						id: 'state',
						label: 'While',
						default: 'program_any',
						choices: choices({ ...STATES, ...Object.fromEntries(LIT.map((id) => [id, QUICK[id]])) }),
					},
				],
				callback: (fb) => !!(this.data && this.data.states && this.data.states[fb.options.state]),
			},
		}
	}

	presets() {
		const presets = {}
		const v = (name) => `$(${this.label}:${name})`
		const style = (text, size = 'auto') => ({ text, size, color: WHITE, bgcolor: DARK })
		const button = (category, name, text, down, feedbacks = []) => ({
			type: 'button',
			category,
			name,
			style: style(text),
			steps: [{ down, up: [] }],
			feedbacks,
		})
		// One Preview and one Program button per graphic.
		for (const g of this.graphics()) {
			const lit = (feedbackId, bgcolor) => ({ feedbackId, options: { graphic: g.id }, style: { bgcolor, color: WHITE } })
			presets[`pvw_${g.id}`] = button(
				'Preview',
				`${g.name}: Preview on / off`,
				g.name,
				[{ actionId: 'preview', options: { graphic: g.id, mode: 'toggle' } }],
				[lit('on_preview', GREEN)],
			)
			presets[`pgm_${g.id}`] = button(
				'Program',
				`${g.name}: in / out on Program`,
				g.name,
				[{ actionId: 'program', options: { graphic: g.id, mode: 'toggle', transition: '' } }],
				[lit('on_program', RED)],
			)
		}
		// Take, clear and update.
		const busLit = (state, bgcolor) => [{ feedbackId: 'state_on', options: { state }, style: { bgcolor, color: WHITE } }]
		presets.take = button('Take', 'Take (the default transition)', `TAKE\n${v('default_transition')}`, [
			{ actionId: 'take', options: { transition: '' } },
		], busLit('preview_any', GREEN))
		for (const t of (this.data && this.data.transitions) || []) {
			presets[`take_${t.id}`] = button('Take', `Take: ${t.name}`, `TAKE\n${t.name}`, [
				{ actionId: 'take', options: { transition: t.id } },
			], busLit('preview_any', GREEN))
		}
		presets.clear_program = button('Take', 'Clear Program', 'CLEAR\nPGM', [
			{ actionId: 'clear', options: { bus: 'program', transition: '' } },
		], busLit('program_any', RED))
		presets.clear_preview = button('Take', 'Clear Preview', 'CLEAR\nPVW', [
			{ actionId: 'clear', options: { bus: 'preview', transition: '' } },
		], busLit('preview_any', GREEN))
		presets.clear_both = button('Take', 'Clear Program and Preview', 'CLEAR\nALL', [
			{ actionId: 'clear', options: { bus: 'both', transition: '' } },
		])
		presets.send = button('Take', 'Update Program (Preview values to air)', 'UPDATE\nPGM', [
			{ actionId: 'send', options: { graphic: '' } },
		])
		// Quick functions.
		const text = {
			score_left_up: `${v('left_short')} +\n${v('left_score')}`,
			score_left_down: `${v('left_short')} −\n${v('left_score')}`,
			score_right_up: `${v('right_short')} +\n${v('right_score')}`,
			score_right_down: `${v('right_short')} −\n${v('right_score')}`,
			score_reset: `SCORE\n0-0`,
			clock_time: 'CLOCK\nTime',
			clock_soon: 'CLOCK\nSoon',
			clock_brb: 'CLOCK\nBRB',
			timer_toggle: `TIMER\n${v('timer')}`,
			timer_reset: 'TIMER\nreset',
			bgloop: 'BG\nloop',
			roster_left: `PLAYERS\n${v('left_short')}`,
			roster_right: `PLAYERS\n${v('right_short')}`,
			caster_1: 'CASTERS\n1',
			caster_2: 'CASTERS\n2',
			caster_3: 'CASTERS\n3',
			caster_4: 'CASTERS\n4',
		}
		for (const [id, name] of Object.entries(QUICK)) {
			const category = name.split(':')[0] === 'Score' ? 'Score' : 'Quick functions'
			presets[`quick_${id}`] = button(
				category,
				name,
				text[id] || name,
				[{ actionId: 'quick', options: { quick: id } }],
				LIT.includes(id) ? [{ feedbackId: 'state_on', options: { state: id }, style: { bgcolor: AMBER, color: BLACK } }] : [],
			)
		}
		presets.on_air = button('Take', 'On air now (shows what is on Program)', `PGM\n${v('program')}`, [])
		return presets
	}
}

runEntrypoint(GfxEngineInstance, [])
