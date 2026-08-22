import { EXIT, getRoot, loadDotEnv } from './config.js';
import { createLogger } from './logger.js';
import { initOtel, shutdown } from './telemetry/otel.js';
import { scrapeCommand } from './commands/scrape.js';
import { promoteCommand } from './commands/promote.js';
import { runCommand } from './commands/run.js';
import { healCommand } from './commands/heal.js';
import { approveCommand } from './commands/approve.js';
import { rejectCommand } from './commands/reject.js';
import { rollbackCommand } from './commands/rollback.js';
import { breakCommand } from './commands/break.js';
import { statusCommand } from './commands/status.js';
import { doctorCommand } from './commands/doctor.js';
import { portSyncCommand } from './commands/port-sync.js';
import { portFlushCommand } from './commands/port-flush.js';
import { validateCommand } from './commands/validate.js';

const COMMANDS = {
  scrape: scrapeCommand,
  promote: promoteCommand,
  run: runCommand,
  heal: healCommand,
  approve: approveCommand,
  reject: rejectCommand,
  rollback: rollbackCommand,
  break: breakCommand,
  status: statusCommand,
  doctor: doctorCommand,
  'port-sync': portSyncCommand,
  'port-flush': portFlushCommand,
  validate: validateCommand,
};

export function parseArgs(argv) {
  const flags = {
    json: false,
    verbose: false,
    dryRun: false,
    force: false,
    collectorId: null,
    url: null,
    input: null,
    prompt: null,
  };
  const rest = [];
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--json') flags.json = true;
    else if (a === '--verbose') flags.verbose = true;
    else if (a === '--dry-run') flags.dryRun = true;
    else if (a === '--force') flags.force = true;
    else if (a === '--collector-id') flags.collectorId = argv[++i];
    else if (a === '--url') flags.url = argv[++i];
    else if (a === '--input') flags.input = argv[++i];
    else if (a === '--prompt') flags.prompt = argv[++i];
    else if (a.startsWith('--collector-id=')) flags.collectorId = a.slice('--collector-id='.length);
    else if (a.startsWith('--url=')) flags.url = a.slice('--url='.length);
    else if (a.startsWith('--input=')) flags.input = a.slice('--input='.length);
    else if (a.startsWith('--prompt=')) flags.prompt = a.slice('--prompt='.length);
    else rest.push(a);
  }
  return { command: rest[0] || null, flags, extra: rest.slice(1) };
}

export async function runFactory(argv, env = process.env) {
  const { command, flags } = parseArgs(argv);
  if (!command || command === 'help' || command === '--help' || command === '-h') {
    const help = [
      'factory <command> [--json] [--verbose] [--dry-run]',
      'commands: scrape validate heal approve reject promote rollback status break run port-sync port-flush doctor',
    ].join('\n');
    if (flags.json) console.log(JSON.stringify({ help }));
    else console.log(help);
    return command && command !== 'help' && command !== '--help' && command !== '-h' ? EXIT.USAGE : EXIT.SUCCESS;
  }
  const handler = COMMANDS[command];
  if (!handler) {
    console.error(`unknown command: ${command}`);
    return EXIT.USAGE;
  }
  const root = getRoot(env);
  loadDotEnv(root, env);
  const log = createLogger({ verbose: flags.verbose, json: flags.json });
  await initOtel({ component: 'pipeline', env });
  const ctx = { root, flags, env, log };
  try {
    const { exitCode, result } = await handler(ctx);
    if (flags.json) console.log(JSON.stringify({ ok: exitCode === 0, command, result }, null, 2));
    else if (result?.error) console.error(result.error);
    return exitCode;
  } catch (err) {
    const code = err.exitCode || EXIT.GENERIC;
    if (flags.json) console.log(JSON.stringify({ ok: false, error: err.message, exitCode: code }));
    else console.error(err.message);
    return code;
  } finally {
    await shutdown();
  }
}
