import { useEffect, useState } from 'react'
import { useJubileeStore } from '../../store/jubileeStore'
import { Button, Card, Dialog, TextInput } from '../ui'

const DEFAULT_PROFILE_NAME = 'Default'

const TRICKLER_FIELDS = [
  ['flow_ema_alpha', 'Flow EMA Alpha', 'number'],
  ['yield_ema_alpha', 'Yield EMA Alpha', 'number'],
  ['jam_yield_threshold', 'Jam Yield Threshold', 'number'],
  ['jam_iter_threshold', 'Jam Iter Threshold', 'number'],
  ['jam_auto_recovery_vibration_amplitude', 'Jam Recovery Vibration', 'number'],
  ['jam_auto_recovery_wait_seconds', 'Jam Recovery Wait Seconds', 'number'],
  ['max_step_size_mm', 'Max Step Size (mm)', 'number'],
  ['min_step_size_mm', 'Min Step Size (mm)', 'number'],
  ['warmup_steps', 'Warmup Steps', 'number'],
  ['warmup_max_step_mm', 'Warmup Max Step (mm)', 'number'],
  ['coarse_threshold_pct', 'Coarse Threshold (%)', 'number'],
  ['finish_threshold_pct', 'Finish Threshold (%)', 'number'],
  ['coarse_target_steps', 'Coarse Target Steps', 'number'],
  ['coarse_feedrate', 'Coarse Feedrate', 'number'],
  ['fine_feedrate', 'Fine Feedrate', 'number'],
  ['coarse_vibration_amplitude', 'Coarse Vibration', 'number'],
  ['fine_vibration_amplitude', 'Fine Vibration', 'number'],
  ['max_dribble_step_mm', 'Max Dribble Step (mm)', 'number'],
]

const HARDNESS_FIELDS = [
  ['__section_shared', 'Shared Settings', 'section'],
  ['num_digits', 'Display Digits', 'number'],
  ['monotonic_drop_threshold', 'Monotonic Drop Threshold', 'number'],
  ['threshold_bias', 'Threshold Bias', 'number'],
  ['sharpen_strength', 'Sharpen Strength', 'number'],
  ['sharpen_blur_radius', 'Sharpen Blur Radius', 'number'],
  ['morph_kernel_size', 'Morph Kernel Size', 'number'],
  ['morph_iterations', 'Morph Iterations', 'number'],
  ['morph_open', 'Morph Open', 'boolean'],
  ['__section_shore_a', 'Shore A Settings', 'section'],
  ['shore_a.use_camera', 'Use Camera', 'boolean'],
  ['shore_a.bypass_cv', 'Bypass CV', 'boolean'],
  ['shore_a.lcd_calibration_path', 'LCD Calibration Path', 'text'],
  ['shore_a.cam_usb_path', 'Camera USB Path', 'text'],
  ['shore_a.button_servos.servo', 'Servo Channel', 'text'],
  ['shore_a.button_servos.power_press_angle', 'Power Press Angle', 'number'],
  ['shore_a.button_servos.power_release_angle', 'Power Release Angle', 'number'],
  ['shore_a.button_servos.zero_press_angle', 'Zero Press Angle', 'number'],
  ['shore_a.button_servos.zero_release_angle', 'Zero Release Angle', 'number'],
  ['__section_shore_d', 'Shore D Settings', 'section'],
  ['shore_d.use_camera', 'Use Camera', 'boolean'],
  ['shore_d.bypass_cv', 'Bypass CV', 'boolean'],
  ['shore_d.lcd_calibration_path', 'LCD Calibration Path', 'text'],
  ['shore_d.cam_usb_path', 'Camera USB Path', 'text'],
  ['shore_d.button_servos.servo', 'Servo Channel', 'text'],
  ['shore_d.button_servos.power_press_angle', 'Power Press Angle', 'number'],
  ['shore_d.button_servos.power_release_angle', 'Power Release Angle', 'number'],
  ['shore_d.button_servos.zero_press_angle', 'Zero Press Angle', 'number'],
  ['shore_d.button_servos.zero_release_angle', 'Zero Release Angle', 'number'],
]

function getNestedValue(profile, key) {
  return key.split('.').reduce((acc, part) => acc?.[part], profile)
}

function setNestedValue(profile, key, value) {
  const parts = key.split('.')
  if (parts.length === 1) return { ...profile, [key]: value }

  const root = { ...profile }
  let node = root
  for (let i = 0; i < parts.length - 1; i += 1) {
    const part = parts[i]
    node[part] = { ...(node?.[part] ?? {}) }
    node = node[part]
  }
  node[parts[parts.length - 1]] = value
  return root
}

function ProfileEditDialog({ open, title, profile, fields, onClose, onSave }) {
  const [draft, setDraft] = useState(profile ?? {})
  const [error, setError] = useState('')

  useEffect(() => {
    if (open) {
      setDraft(profile ?? {})
      setError('')
    }
  }, [open, profile])

  function updateField(key, type, rawValue) {
    let value = rawValue
    if (type === 'boolean') value = rawValue === 'true'
    if (type === 'number') value = rawValue === '' ? '' : Number(rawValue)
    setDraft((prev) => setNestedValue(prev, key, value))
  }

  function handleSave() {
    try {
      const normalized = {}
      for (const [key, _label, type] of fields) {
        if (type === 'section') continue
        const value = getNestedValue(draft, key)
        if (type === 'number') {
          if (value === '' || Number.isNaN(Number(value))) {
            throw new Error(`Invalid numeric value for ${key}`)
          }
          Object.assign(normalized, setNestedValue(normalized, key, Number(value)))
          continue
        }
        if (type === 'boolean') {
          Object.assign(normalized, setNestedValue(normalized, key, Boolean(value)))
          continue
        }
        Object.assign(normalized, setNestedValue(normalized, key, String(value ?? '')))
      }
      onSave(normalized)
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <Dialog
      open={open}
      title={title}
      onClose={onClose}
      width="max-w-2xl"
      footer={(
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave}>Save</Button>
        </>
      )}
    >
      <div className="max-h-[60vh] overflow-y-auto pr-2 flex flex-col gap-3">
        {fields.map(([key, label, type]) => {
          if (type === 'section') {
            return (
              <p
                key={key}
                className="text-xs font-semibold uppercase tracking-widest text-slate-300 mt-2"
              >
                {label}
              </p>
            )
          }
          const value = getNestedValue(draft, key)
          if (type === 'boolean') {
            return (
              <label key={key} className="flex flex-col gap-1">
                <span className="text-xs font-medium uppercase tracking-widest text-slate-400">
                  {label}
                </span>
                <select
                  className="w-full h-12 bg-slate-900 border border-slate-600 rounded-xl px-4 text-slate-100 text-sm focus:outline-none focus:border-jubilee"
                  value={String(Boolean(value))}
                  onChange={(e) => updateField(key, type, e.target.value)}
                >
                  <option value="true">True</option>
                  <option value="false">False</option>
                </select>
              </label>
            )
          }
          return (
            <TextInput
              key={key}
              label={label}
              type={type}
              value={value ?? ''}
              onChange={(next) => updateField(key, type, next)}
            />
          )
        })}
      </div>
      {error && <p className="text-xs text-red-400 mt-3">{error}</p>}
    </Dialog>
  )
}

function CopyProfileDialog({ open, title, onClose, onCopy }) {
  const [name, setName] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (open) {
      setName('')
      setError('')
    }
  }, [open])

  function handleCopy() {
    const trimmed = name.trim()
    if (!trimmed) {
      setError('Name is required.')
      return
    }
    onCopy(trimmed)
  }

  return (
    <Dialog
      open={open}
      title={title}
      onClose={onClose}
      footer={(
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={handleCopy}>Copy</Button>
        </>
      )}
    >
      <TextInput
        label="New Profile Name"
        value={name}
        onChange={setName}
        placeholder="new_profile"
      />
      {error && <p className="text-xs text-red-400 mt-3">{error}</p>}
    </Dialog>
  )
}

export function TricklerProfilesSection({ locked }) {
  const data = useJubileeStore((s) => s.tricklerProfiles)
  const error = useJubileeStore((s) => s.tricklerProfilesError)
  const fetchProfiles = useJubileeStore((s) => s.fetchTricklerProfiles)
  const createProfile = useJubileeStore((s) => s.createTricklerProfile)
  const setActiveProfile = useJubileeStore((s) => s.setActiveTricklerProfile)
  const updateProfile = useJubileeStore((s) => s.updateTricklerProfile)
  const deleteProfile = useJubileeStore((s) => s.deleteTricklerProfile)
  const [statusMsg, setStatusMsg] = useState('')
  const [editing, setEditing] = useState(false)
  const [copying, setCopying] = useState(false)

  useEffect(() => { fetchProfiles() }, [fetchProfiles])

  if (!data) {
    return (
      <Card className="p-5">
        <h3 className="text-sm font-semibold uppercase tracking-widest text-slate-400">
          Trickler Configuration
        </h3>
        <p className="text-xs text-slate-500 mt-2">Loading profiles...</p>
      </Card>
    )
  }

  const active = data.active_profile
  const profileNames = Object.keys(data.profiles ?? {})
  const activeProfile = data.profiles?.[active] ?? null
  const editLocked = locked || data.edits_locked

  async function handleSelect(nextName) {
    setStatusMsg('')
    const result = await setActiveProfile(nextName)
    if (!result.ok) setStatusMsg(result.error ?? 'Failed to select profile.')
  }

  async function handleSave(nextProfile) {
    const result = await updateProfile(active, nextProfile)
    if (!result.ok) {
      setStatusMsg(result.error ?? 'Failed to save profile.')
      return
    }
    setEditing(false)
  }

  async function handleCopy(name) {
    const result = await createProfile(name, active)
    if (!result.ok) {
      setStatusMsg(result.error ?? 'Failed to copy profile.')
      return
    }
    setCopying(false)
  }

  async function handleDelete() {
    const result = await deleteProfile(active)
    if (!result.ok) {
      setStatusMsg(result.error ?? 'Failed to delete profile.')
    }
  }

  return (
    <Card className="flex flex-col gap-4 p-5">
      <h3 className="text-sm font-semibold uppercase tracking-widest text-slate-400">
        Trickler Configuration
      </h3>
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium uppercase tracking-widest text-slate-400">
          Profile
        </label>
        <select
          className="w-full h-12 bg-slate-900 border border-slate-600 rounded-xl px-4 text-slate-100 text-sm focus:outline-none focus:border-jubilee disabled:opacity-40"
          value={active}
          onChange={(e) => handleSelect(e.target.value)}
          disabled={editLocked}
        >
          {profileNames.map((name) => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" variant="outlined" onClick={() => setEditing(true)} disabled={editLocked}>
          Edit
        </Button>
        <Button size="sm" variant="outlined" onClick={() => setCopying(true)} disabled={editLocked}>
          Copy
        </Button>
        <Button
          size="sm"
          variant="danger"
          onClick={handleDelete}
          disabled={editLocked || active === DEFAULT_PROFILE_NAME}
        >
          Delete
        </Button>
      </div>
      <p className="text-xs text-slate-500">
        Default profile is always available. Profile edits are locked after connection begins.
      </p>
      {editLocked && (
        <p className="text-xs text-amber-400">
          Profiles are locked for this server session. Restart backend to edit.
        </p>
      )}
      {error && <p className="text-xs text-red-400">{error}</p>}
      {statusMsg && <p className="text-xs text-red-400">{statusMsg}</p>}
      <ProfileEditDialog
        open={editing}
        title={`Edit Trickler Profile: ${active}`}
        profile={activeProfile}
        fields={TRICKLER_FIELDS}
        onClose={() => setEditing(false)}
        onSave={handleSave}
      />
      <CopyProfileDialog
        open={copying}
        title="Copy Trickler Profile"
        onClose={() => setCopying(false)}
        onCopy={handleCopy}
      />
    </Card>
  )
}

export function HardnessProfilesSection({ locked }) {
  const data = useJubileeStore((s) => s.hardnessProfiles)
  const error = useJubileeStore((s) => s.hardnessProfilesError)
  const fetchProfiles = useJubileeStore((s) => s.fetchHardnessProfiles)
  const createProfile = useJubileeStore((s) => s.createHardnessProfile)
  const setActiveProfile = useJubileeStore((s) => s.setActiveHardnessProfile)
  const updateProfile = useJubileeStore((s) => s.updateHardnessProfile)
  const deleteProfile = useJubileeStore((s) => s.deleteHardnessProfile)
  const [statusMsg, setStatusMsg] = useState('')
  const [editing, setEditing] = useState(false)
  const [copying, setCopying] = useState(false)

  useEffect(() => { fetchProfiles() }, [fetchProfiles])

  if (!data) {
    return (
      <Card className="p-5">
        <h3 className="text-sm font-semibold uppercase tracking-widest text-slate-400">
          Hardness Testing Configuration
        </h3>
        <p className="text-xs text-slate-500 mt-2">Loading profiles...</p>
      </Card>
    )
  }

  const active = data.active_profile
  const profileNames = Object.keys(data.profiles ?? {})
  const activeProfile = data.profiles?.[active] ?? null
  const editLocked = locked || data.edits_locked

  async function handleSelect(nextName) {
    setStatusMsg('')
    const result = await setActiveProfile(nextName)
    if (!result.ok) setStatusMsg(result.error ?? 'Failed to select profile.')
  }

  async function handleSave(nextProfile) {
    const result = await updateProfile(active, nextProfile)
    if (!result.ok) {
      setStatusMsg(result.error ?? 'Failed to save profile.')
      return
    }
    setEditing(false)
  }

  async function handleCopy(name) {
    const result = await createProfile(name, active)
    if (!result.ok) {
      setStatusMsg(result.error ?? 'Failed to copy profile.')
      return
    }
    setCopying(false)
  }

  async function handleDelete() {
    const result = await deleteProfile(active)
    if (!result.ok) {
      setStatusMsg(result.error ?? 'Failed to delete profile.')
    }
  }

  return (
    <Card className="flex flex-col gap-4 p-5">
      <h3 className="text-sm font-semibold uppercase tracking-widest text-slate-400">
        Hardness Testing Configuration
      </h3>
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium uppercase tracking-widest text-slate-400">
          Profile
        </label>
        <select
          className="w-full h-12 bg-slate-900 border border-slate-600 rounded-xl px-4 text-slate-100 text-sm focus:outline-none focus:border-jubilee disabled:opacity-40"
          value={active}
          onChange={(e) => handleSelect(e.target.value)}
          disabled={editLocked}
        >
          {profileNames.map((name) => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" variant="outlined" onClick={() => setEditing(true)} disabled={editLocked}>
          Edit
        </Button>
        <Button size="sm" variant="outlined" onClick={() => setCopying(true)} disabled={editLocked}>
          Copy
        </Button>
        <Button
          size="sm"
          variant="danger"
          onClick={handleDelete}
          disabled={editLocked || active === DEFAULT_PROFILE_NAME}
        >
          Delete
        </Button>
      </div>
      <p className="text-xs text-slate-500">
        Hardness profile editor includes shared settings plus Shore A and Shore D sections.
      </p>
      {editLocked && (
        <p className="text-xs text-amber-400">
          Profiles are locked for this server session. Restart backend to edit.
        </p>
      )}
      {error && <p className="text-xs text-red-400">{error}</p>}
      {statusMsg && <p className="text-xs text-red-400">{statusMsg}</p>}
      <ProfileEditDialog
        open={editing}
        title={`Edit Hardness Profile: ${active}`}
        profile={activeProfile}
        fields={HARDNESS_FIELDS}
        onClose={() => setEditing(false)}
        onSave={handleSave}
      />
      <CopyProfileDialog
        open={copying}
        title="Copy Hardness Profile"
        onClose={() => setCopying(false)}
        onCopy={handleCopy}
      />
    </Card>
  )
}
