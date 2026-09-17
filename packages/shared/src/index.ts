export const FRAMEWORK_NAME = 'V3-AIDLC';
export const FRAMEWORK_VERSION = '0.1.0';

export interface HealthReport {
  readonly service: string;
  readonly status: 'ok' | 'degraded';
  readonly version: string;
}

export function healthReport(service: string): HealthReport {
  return { service, status: 'ok', version: FRAMEWORK_VERSION };
}
