const counters = new Map();
const histograms = new Map();

function bump(map, name, value, attrs) {
  const key = `${name}:${JSON.stringify(attrs || {})}`;
  const prev = map.get(key) || { name, value: 0, attrs: attrs || {} };
  prev.value += value;
  map.set(key, prev);
}

export function increment(name, attrs = {}, by = 1) {
  bump(counters, name, by, attrs);
}

export function recordMs(name, ms, attrs = {}) {
  bump(histograms, name, ms, attrs);
}

export function snapshot() {
  return {
    counters: [...counters.values()],
    histograms: [...histograms.values()],
  };
}

export function resetMetrics() {
  counters.clear();
  histograms.clear();
}
