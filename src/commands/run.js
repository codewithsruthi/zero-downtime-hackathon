import { EXIT } from '../config.js';
import { scrapeCommand } from './scrape.js';
import { promoteCommand } from './promote.js';
import { injectTraceparentIntoEnv } from '../telemetry/context.js';
import { withSpan } from '../telemetry/otel.js';

export async function runCommand(ctx) {
  return withSpan('factory.run', { 'factory.component': 'pipeline' }, async () => {
    injectTraceparentIntoEnv(ctx.env);
    const scraped = await scrapeCommand(ctx);
    if (scraped.exitCode !== EXIT.SUCCESS) return scraped;
    return promoteCommand(ctx);
  });
}
