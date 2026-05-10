/**
 * Physical dispensing bed layout constants.
 *
 * Layout (top = farthest from operator, bottom = closest to trickler):
 *   Row 0: 7 molds across (IDs 0-6)
 *   Row 1: 7 molds across (IDs 7-13)
 *   Row 2: 2 molds | scale access | 2 molds  (IDs 14-17; null = scale column)
 *   [trickler below row 2]
 *
 * Well IDs are numbered left-to-right, top-to-bottom, skipping scale positions.
 */

export const DISPENSING_LAYOUT = [
  [0,  1,  2,  3,  4,  5,  6],
  [7,  8,  9, 10, 11, 12, 13],
  [14, 15, null, null, null, 16, 17],
]

export const DISPENSING_ROWS        = DISPENSING_LAYOUT.length
export const DISPENSING_COLS        = DISPENSING_LAYOUT[0].length
export const DISPENSING_WELL_COUNT  = 18
