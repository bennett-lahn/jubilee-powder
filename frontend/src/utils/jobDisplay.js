import { DISPENSING_LAYOUT } from '../constants/dispensingBed'
import { HARDNESS_TRAY_COUNT } from '../constants/hardnessTray'
import { sampleKeyForTray } from '../components/SampleTrayGrid'

export function formatJobDate(job) {
  if (!job) return null
  const raw = job.date ?? (job.started_at ? job.started_at.slice(0, 10) : null)
  if (!raw) return null
  const [y, m, d] = raw.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  })
}

export function buildResultWells(rows, cols, job, jobType) {
  const wells = {}

  if (jobType === 'hardness') {
    const total = rows * cols
    for (let trayIndex = 0; trayIndex < HARDNESS_TRAY_COUNT; trayIndex++) {
      for (let sampleIndex = 0; sampleIndex < total; sampleIndex++) {
        const id = sampleKeyForTray(trayIndex, sampleIndex)
        wells[id] = {
          selected:      false,
          targetWeight:  0,
          currentWeight: 0,
          mode:          'none',
          status:        'excluded',
          actualWeight:  null,
          result:        null,
          resultShoreA:  null,
          resultShoreD:  null,
          sampleError:   null,
        }
      }
    }
  } else {
    DISPENSING_LAYOUT.flat().filter((id) => id !== null).forEach((id) => {
      wells[String(id)] = {
        selected:      false,
        targetWeight:  0,
        currentWeight: 0,
        mode:          'none',
        status:        'excluded',
        actualWeight:  null,
        result:        null,
        resultShoreA:  null,
        resultShoreD:  null,
        sampleError:   null,
      }
    })
  }

  const items = job?.items
  if (!items?.length) return wells

  items.forEach((item, idx) => {
    const id = item.well_id != null
      ? String(item.well_id)
      : sampleKeyForTray(item.tray_index, item.sample_index)
    if (!(id in wells)) return

    let status
    if (item.status) {
      status = item.status
    } else if (item.sample_error) {
      status = 'error'
    } else if (idx < (job.completed ?? 0)) {
      status = 'complete'
    } else if (String(job.current_item) === id) {
      status = 'active'
    } else {
      status = 'incomplete'
    }

    wells[id] = {
      ...wells[id],
      targetWeight: item.target_weight ?? 0,
      actualWeight: item.actual_weight ?? null,
      result: null,
      resultShoreA: item.result_shore_a ?? null,
      resultShoreD: item.result_shore_d ?? null,
      sampleError: item.sample_error ?? null,
      mode: item.mode ?? 'none',
      status,
    }
  })

  return wells
}
