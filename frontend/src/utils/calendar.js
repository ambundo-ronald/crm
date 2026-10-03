// Date-only arithmetic is UTC; appointment datetimes remain site-local wall times.
export function shiftDate(value, days) {
  const date = new Date(value + 'T12:00:00Z')
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}
export function monthStart(value) {
  return value.slice(0, 7) + '-01'
}
export function shiftMonth(value, amount) {
  const date = new Date(monthStart(value) + 'T12:00:00Z')
  date.setUTCMonth(date.getUTCMonth() + amount)
  return date.toISOString().slice(0, 10)
}
export function calendarRange(value, view) {
  if (view === 'Day') return { start: value, end: shiftDate(value, 1) }
  if (view === 'Schedule') return { start: value, end: shiftDate(value, 31) }
  const anchor = view === 'Month' ? monthStart(value) : value
  const day = new Date(anchor + 'T12:00:00Z').getUTCDay()
  const start = shiftDate(anchor, -((day + 6) % 7))
  const days = view === 'Month' ? 42 : 7
  return { start, end: shiftDate(start, days) }
}
export function datesBetween(start, end) {
  const result = []
  for (let value = start; value < end; value = shiftDate(value, 1))
    result.push(value)
  return result
}
export function dayEvents(events, date) {
  const start = date + ' 00:00:00'
  const end = shiftDate(date, 1) + ' 00:00:00'
  return events
    .filter(
      (row) =>
        row.starts_on?.replace('T', ' ') < end &&
        row.ends_on?.replace('T', ' ') > start,
    )
    .sort(
      (a, b) =>
        a.starts_on.localeCompare(b.starts_on) || a.name.localeCompare(b.name),
    )
}
export function timeLayout(events, date) {
  const minutes = (value) =>
    Number(value.slice(11, 13)) * 60 + Number(value.slice(14, 16))
  const items = dayEvents(events, date).map((row) => ({
    row,
    start: row.starts_on.slice(0, 10) < date ? 0 : minutes(row.starts_on),
    end: row.ends_on.slice(0, 10) > date ? 1440 : minutes(row.ends_on),
  }))
  let group = [],
    groupEnd = -1
  function place() {
    const ends = []
    for (const item of group) {
      // Minimum visual height is 20 minutes; layout also separates short adjacent events.
      let lane = ends.findIndex((end) => end <= item.start)
      if (lane === -1) lane = ends.length
      ends[lane] = Math.max(item.end, item.start + 20)
      item.lane = lane
    }
    for (const item of group) item.lanes = ends.length
  }
  for (const item of items) {
    if (item.start >= groupEnd) {
      place()
      group = []
      groupEnd = -1
    }
    group.push(item)
    groupEnd = Math.max(groupEnd, item.end, item.start + 20)
  }
  place()
  return items.map((item) => ({
    ...item,
    style: {
      top: `${(item.start / 1440) * 100}%`,
      height: `${(Math.max(item.end - item.start, 20) / 1440) * 100}%`,
      left: `calc(${(item.lane / item.lanes) * 100}% + 2px)`,
      width: `calc(${100 / item.lanes}% - 4px)`,
    },
  }))
}
