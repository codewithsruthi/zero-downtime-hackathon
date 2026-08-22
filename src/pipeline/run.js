import { scrapeCommand } from '../commands/scrape.js';
import { promoteCommand } from '../commands/promote.js';
import { injectTraceparentIntoEnv } from '../telemetry/context.js';
import { withSpan } from '../telemetry/otel.js';

export async function runPipeline(ctx) {
  return withSpan('factory.run', { 'factory.component': 'pipeline' }, async () => {
    injectTraceparentIntoEnv(ctx.env);
    const scraped = await scrapeCommand(ctx);
    if (scraped.exitCode !== 0) return scraped;
    return promoteCommand(ctx);
  });
}
