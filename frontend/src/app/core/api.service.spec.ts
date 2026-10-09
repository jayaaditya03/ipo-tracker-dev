import { HttpErrorResponse } from '@angular/common/http';

import { errorText } from './api.service';

const err = (status: number, error: unknown) => new HttpErrorResponse({ status, error });

describe('errorText', () => {
  it('explains an unreachable server', () => {
    expect(errorText(err(0, new ProgressEvent('error')))).toContain("Can't reach the IPO-PRO server");
  });

  it('shows detail and non-field errors bare, field errors with their name', () => {
    expect(errorText(err(400, { detail: 'Nope.' }))).toBe('Nope.');
    expect(errorText(err(400, { lots: ['Too many.'], non_field_errors: ['Bad.'] }))).toBe('lots: Too many. · Bad.');
  });

  it('passes through the throttle message', () => {
    const body = { detail: 'Request was throttled. Expected available in 42 seconds.' };
    expect(errorText(err(429, body))).toBe(body.detail);
  });

  it('handles string and empty bodies', () => {
    expect(errorText(err(500, 'Server Error'))).toBe('Server Error');
    expect(errorText(err(500, null))).toContain('Something went wrong');
  });
});
