import { Component, input } from '@angular/core';

import { CheckOutcome, CheckResponse } from '../core/models';

const LABELS: Record<CheckOutcome, string> = {
  allotted: 'Allotted',
  not_allotted: 'Not allotted',
  not_found: 'No record',
  not_published: 'Not out yet',
  unsupported: 'Check manually',
  error: 'Failed',
};

const TONES: Record<CheckOutcome, string> = {
  allotted: 'good',
  not_allotted: 'bad',
  not_found: 'muted',
  not_published: 'muted',
  unsupported: 'neutral',
  error: 'bad',
};

/** Per-PAN outcome of an allotment check. */
@Component({
  selector: 'app-check-results',
  template: `
    @if (data(); as d) {
      @if (d.results.length) {
        <div class="table-wrap"><table>
          <thead><tr><th>IPO</th><th>Applicant</th><th>Result</th><th class="num">Allotted</th><th></th></tr></thead>
          <tbody>
            @for (r of d.results; track r.application_id) {
              <tr>
                <td>{{ r.ipo_name }}</td>
                <td>{{ r.pan_label }} <span class="muted">{{ r.pan_masked }}</span></td>
                <td><span class="badge" [class]="tones[r.outcome]">{{ labels[r.outcome] }}</span></td>
                <td class="num">{{ r.outcome === 'allotted' ? r.shares_allotted + ' / ' + r.shares_applied : '—' }}</td>
                <td class="muted">
                  {{ r.message }}
                  @if ((r.outcome === 'unsupported' || r.outcome === 'error') && r.status_check_url) {
                    <a [href]="r.status_check_url" target="_blank" rel="noopener">{{ r.registrar }} ↗</a>
                  }
                </td>
              </tr>
            }
          </tbody>
        </table></div>
      } @else {
        <p class="muted">Nothing to check — no applied, unresolved applications whose allotment date has arrived.</p>
      }
    }
  `,
})
export class CheckResults {
  readonly data = input<CheckResponse | null>(null);
  labels = LABELS;
  tones = TONES;
}
