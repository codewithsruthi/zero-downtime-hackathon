export function extractFirstJson(text) {
  if (!text) return null;
  let start = -1;
  for (let i = 0; i < text.length; i += 1) {
    if (text[i] === '{' || text[i] === '[') {
      start = i;
      break;
    }
  }
  if (start === -1) return null;
  const stack = [];
  let inStr = false;
  let esc = false;
  for (let i = start; i < text.length; i += 1) {
    const c = text[i];
    if (inStr) {
      if (esc) {
        esc = false;
        continue;
      }
      if (c === '\\') {
        esc = true;
        continue;
      }
      if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') {
      inStr = true;
      continue;
    }
    if (c === '{' || c === '[') stack.push(c);
    else if (c === '}' || c === ']') {
      const open = stack.pop();
      if ((c === '}' && open !== '{') || (c === ']' && open !== '[')) return null;
      if (stack.length === 0) {
        try {
          return JSON.parse(text.slice(start, i + 1));
        } catch {
          return null;
        }
      }
    }
  }
  return null;
}

export function classify({ exitCode, stdout = '', stderr = '', parsed = null, timedOut = false }) {
  if (parsed != null) return { code: 'OK', parsed };
  const text = `${stdout}\n${stderr}`.toLowerCase();
  if (timedOut || exitCode === null) return { code: 'FAIL_TIMEOUT', parsed: null };
  if (/unauthor|api key|auth|forbidden|401|403/.test(text)) return { code: 'FAIL_AUTH', parsed: null };
  if (/not found|unknown collector|no such|404/.test(text)) return { code: 'FAIL_NOT_FOUND', parsed: null };
  if (/timeout|etimedout/.test(text)) return { code: 'FAIL_TIMEOUT', parsed: null };
  return { code: 'FAIL_PARSE', parsed: null };
}

export function exitForClass(code) {
  if (code === 'OK') return 0;
  if (code === 'FAIL_PARSE') return 10;
  return 5;
}
