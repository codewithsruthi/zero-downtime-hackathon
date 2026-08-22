const LEVELS = { error: 0, warn: 1, info: 2, debug: 3 };

function nowIso() {
  return new Date().toISOString();
}

export function createLogger({ verbose = false, json = false } = {}) {
  const min = verbose ? LEVELS.debug : LEVELS.info;

  function write(level, msg, extra) {
    if (LEVELS[level] > min) return;
    const rec = { ts: nowIso(), level, msg, ...(extra && typeof extra === 'object' ? extra : {}) };
    const line = json ? JSON.stringify(rec) : `${rec.ts} [${level}] ${msg}${extra ? ` ${JSON.stringify(extra)}` : ''}`;
    console.error(line);
  }

  return {
    error: (msg, extra) => write('error', msg, extra),
    warn: (msg, extra) => write('warn', msg, extra),
    info: (msg, extra) => write('info', msg, extra),
    debug: (msg, extra) => write('debug', msg, extra),
  };
}

export const logger = createLogger({ verbose: process.env.FACTORY_VERBOSE === '1' });
