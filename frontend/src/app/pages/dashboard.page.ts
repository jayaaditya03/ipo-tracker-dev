import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService, errorText } from '../core/api.service';
import { Application, CheckResponse, DashboardSummary, Ipo } from '../core/models';
import { CheckResults } from '../shared/check-results';
import { InrPipe } from '../shared/format';

@Component({
  imports: [RouterLink, InrPipe, DatePipe, CheckResults],
  template: `
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
      <h4 class="mb-0">Dashboard</h4>
      @if (waiting().length) {
        <button class="btn btn-primary btn-sm" (click)="check()" [disabled]="checking()">
          {{ checking() ? 'Checking with registrars…' : 'Check pending allotments' }}
        </button>
      }
    </div>
    @if (error()) { <div class="alert alert-danger">{{ error() }}</div> }

    @if (checkResult()) {
      <div class="card">
        <div class="card-header"><h5 class="mb-0">Allotment check</h5></div>
        <div class="card-body pt-0"><app-check-results [data]="checkResult()" /></div>
      </div>
    }

    @if (s(); as s) {
      <div class="row">
        @for (t of tiles(); track t.label) {
          <div class="col-6 col-md-4 col-xl-2">
            <div class="card stat-card">
              <div class="card-body">
                <h6 class="mb-2 f-w-400 text-muted">{{ t.label }}</h6>
                <div class="stat-value" [class.text-gain]="t.tone === 'gain'" [class.text-loss]="t.tone === 'loss'">{{ t.value }}</div>
                <p class="mb-0 text-muted text-sm">{{ t.hint }}</p>
              </div>
            </div>
          </div>
        }
      </div>

      <div class="row">
        <div class="col-xl-6">
          <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
              <h5 class="mb-0">Awaiting result</h5>
              <a routerLink="/applications" class="link-primary text-sm">All applications →</a>
            </div>
            <div class="table-responsive">
              <table class="table table-hover mb-0">
                <thead><tr><th>IPO</th><th>Applicant</th><th>Allotment</th></tr></thead>
                <tbody>
                  @for (a of waiting(); track a.id) {
                    <tr>
                      <td><a [routerLink]="['/ipos', a.ipo.id]">{{ a.ipo.name }}</a></td>
                      <td>{{ a.pan_label }}</td>
                      <td>{{ (a.ipo.allotment_date | date: 'd MMM') ?? '—' }}</td>
                    </tr>
                  } @empty {
                    <tr><td colspan="3" class="text-center text-muted py-4">Nothing waiting for a result.</td></tr>
                  }
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="col-xl-6">
          <div class="card">
            <div class="card-header"><h5 class="mb-0">By applicant</h5></div>
            <div class="table-responsive">
              <table class="table table-hover mb-0">
                <thead><tr><th>Applicant</th><th class="num">Applied</th><th class="num">Allotted</th><th class="num">Hit rate</th></tr></thead>
                <tbody>
                  @for (p of s.by_pan; track p.pan__id) {
                    <tr>
                      <td>{{ p.pan__label }}</td>
                      <td class="num">{{ p.applications }}</td>
                      <td class="num">{{ p.allotted }}</td>
                      <td class="num">{{ p.applications ? ((p.allotted / p.applications) * 100).toFixed(0) : 0 }}%</td>
                    </tr>
                  } @empty {
                    <tr><td colspan="4" class="text-center text-muted py-4">
                      No applications yet. <a routerLink="/pans">Add a PAN</a>, then pick an <a routerLink="/ipos">IPO</a>.
                    </td></tr>
                  }
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    }

    <div class="card">
      <div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0">Open for bidding today</h5>
        <a routerLink="/ipos" class="link-primary text-sm">All IPOs →</a>
      </div>
      <div class="table-responsive">
        <table class="table table-hover mb-0">
          <thead><tr><th>Issue</th><th>Board</th><th>Closes</th><th class="num">Price</th><th class="num">Min. amount</th><th></th></tr></thead>
          <tbody>
            @for (i of open(); track i.id) {
              <tr>
                <td><a [routerLink]="['/ipos', i.id]">{{ i.name }}</a></td>
                <td>{{ i.board === 'SME' ? 'SME' : 'Mainboard' }}</td>
                <td>{{ i.close_date | date: 'd MMM' }}</td>
                <td class="num">{{ i.cutoff_price | inr }}</td>
                <td class="num">{{ i.lot_amount | inr }}</td>
                <td class="text-end"><a [routerLink]="['/ipos', i.id]" class="btn btn-sm btn-primary">Apply</a></td>
              </tr>
            } @empty {
              <tr><td colspan="6" class="text-center text-muted py-4">Nothing is open for bidding today.</td></tr>
            }
          </tbody>
        </table>
      </div>
    </div>
  `,
})
export class DashboardPage {
  private api = inject(ApiService);
  private inr = new InrPipe();

  s = signal<DashboardSummary | null>(null);
  open = signal<Ipo[]>([]);
  waiting = signal<Application[]>([]);
  checking = signal(false);
  checkResult = signal<CheckResponse | null>(null);
  error = signal('');

  tiles = computed(() => {
    const s = this.s();
    if (!s) return [];
    const gain = Number(s.realised_gain);
    return [
      { label: 'Applications', value: String(s.applications), hint: `${s.pending} awaiting result` },
      { label: 'Allotted', value: String(s.allotted), hint: `${s.rejected} not allotted` },
      { label: 'Hit rate', value: `${s.hit_rate}%`, hint: 'of resolved applications' },
      { label: 'Money blocked', value: this.inr.transform(s.blocked), hint: 'in pending ASBA mandates' },
      { label: 'Invested', value: this.inr.transform(s.invested), hint: 'in allotted shares' },
      { label: 'Listing gain', value: this.inr.transform(s.realised_gain), hint: 'where listing price is known',
        tone: gain > 0 ? 'gain' : gain < 0 ? 'loss' : '' },
    ];
  });

  constructor() {
    this.load();
    this.api.openNow().subscribe((o) => this.open.set(o));
  }

  load() {
    this.api.summary().subscribe({ next: (s) => this.s.set(s), error: (e) => this.error.set(errorText(e)) });
    this.api.applications({ status: 'APPLIED', ordering: 'ipo__allotment_date', page_size: 10 })
      .subscribe((p) => this.waiting.set(p.results));
  }

  check() {
    this.checking.set(true);
    this.error.set('');
    this.api.checkAllotments().subscribe({
      next: (r) => { this.checkResult.set(r); this.checking.set(false); this.load(); },
      error: (e) => { this.error.set(errorText(e)); this.checking.set(false); },
    });
  }
}
