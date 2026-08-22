import { initOtel } from '../src/telemetry/otel.js';

await initOtel({ component: 'app', env: process.env });
