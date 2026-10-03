import { describe, it, expect } from 'vitest'
import {
  calendarRange,
  shiftDate,
  shiftMonth,
  dayEvents,
  timeLayout,
} from '../../src/utils/calendar'
const event = (name, start, end) => ({
  name,
  starts_on: `2035-06-14 ${start}:00`,
  ends_on: `2035-06-14 ${end}:00`,
})
describe('calendar dates and event placement', () => {
  it('uses Monday weeks and full month grids across year boundaries', () => {
    expect(calendarRange('2026-01-01', 'Week')).toEqual({
      start: '2025-12-29',
      end: '2026-01-05',
    })
    expect(calendarRange('2026-01-01', 'Month')).toEqual({
      start: '2025-12-29',
      end: '2026-02-09',
    })
  })
  it('handles leap days and month navigation without overflowing short months', () => {
    expect(shiftDate('2028-02-28', 1)).toBe('2028-02-29')
    expect(shiftMonth('2028-01-31', 1)).toBe('2028-02-01')
    expect(shiftMonth('2026-01-31', -1)).toBe('2025-12-01')
  })
  it('includes spanning events, excluding an event ending at midnight', () => {
    const rows = [
      {
        name: 'span',
        starts_on: '2035-06-13 23:00:00',
        ends_on: '2035-06-15 00:00:00',
      },
    ]
    expect(dayEvents(rows, '2035-06-14')).toHaveLength(1)
    expect(dayEvents(rows, '2035-06-15')).toHaveLength(0)
    expect(timeLayout(rows, '2035-06-14')[0]).toMatchObject({
      start: 0,
      end: 1440,
    })
  })
  it('separates overlapping events and releases a lane at the boundary', () => {
    const rows = [
      event('a', '10:00', '11:00'),
      event('b', '10:30', '12:00'),
      event('c', '11:00', '11:30'),
      event('d', '13:00', '14:00'),
    ]
    expect(
      timeLayout(rows, '2035-06-14').map(({ lane, lanes }) => [lane, lanes]),
    ).toEqual([
      [0, 2],
      [1, 2],
      [0, 2],
      [0, 1],
    ])
  })
  it('separates very short appointments visually', () => {
    expect(
      timeLayout(
        [event('a', '10:00', '10:05'), event('b', '10:06', '10:10')],
        '2035-06-14',
      ).map((row) => row.lanes),
    ).toEqual([2, 2])
  })
})
