import { DatePipe } from '@angular/common';
import { Component, effect, inject, input, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Subject, debounceTime } from 'rxjs';

import { ApiService, errorText } from '../core/api.service';
import { APP_STATUS_LABELS, AppStatus, Application, CheckResponse, Page, Pan, StatusEvent } from '../core/models';
import { CheckResults } from '../shared/check-results';
import { InrPipe, TonePipe } from '../shared/format';

@Component({
  imports: [FormsModule, RouterLink, DatePipe, InrPipe, TonePipe, CheckResults],
  template: `
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
      <h4 class="mb-0">Applications</h4>
      <div class="d-flex flex-wrap gap-2">
        <input class="form-control form-control-sm" style="width: 190px" [(ngModel)]="search" (ngModelChange)="typed.next()"
          placeholder="Search IPO" aria-label="Search IPO" />
        <select class="form-select form-select-sm" style="width: 160px" [(ngModel)]="pan" (ngModelChange)="load(1)" aria-label="Applicant">
          <option value="">All applicants</option>
          @for (p of pans(); track p.id) { <option [value]="p.id">{{ p.label }}</option> }
        </select>
        <select class="form-select form-select-sm" style="width: 170px" [(ngModel)]="result" (ngModelChange)="load(1)" aria-label="Result">
          @for (r of resultFilters; track r.label) { <option [value]="r.value">{{ r.label }}</option> }
        </select>
        <button class="btn btn-sm btn-primary" (click)="checkAll()" [disabled]="checking()">
          {{ checking() ? 'Checking with registrars…' : 'Check pending allotments' }}
        </button>
      </div>
    </div>

    @if (ipo()) { <div class="alert alert-info py-2">Showing one issue. <a routerLink="/applications" class="alert-link">Show all</a></div> }
    @if (error()) { <div class="alert alert-danger">{{ error() }}</div> }

    @if (checkResult()) {
      <div class="card">
        <div class="card-header"><h5 class="mb-0">Allotment check</h5></div>
        <div class="card-body pt-0"><app-check-results [data]="checkResult()" /></div>
      </div>
    }

    <div class="card">
      <div class="table-responsive">
        <table class="table table-hover mb-0">
          <thead>
            <tr>
              <th>IPO</th><th>Applicant</th><th class="num">Lots</th><th class="num">Blocked</th>
              <th>Result</th><th class="num">Allotted</th><th class="num">Gain</th><th></th>
            </tr>
          </thead>
          <tbody>
            @for (a of page()?.results; track a.id) {
              <tr>
                <td>
                  <a [routerLink]="['/ipos', a.ipo.id]" class="f-w-600">{{ a.ipo.name }}</a>
                  <div class="text-muted text-sm">
                    Allotment {{ (a.ipo.allotment_date | date: 'd MMM') ?? '—' }}
                    @if (a.ipo.registrar.status_check_url) {
                      · <a [href]="a.ipo.registrar.status_check_url" target="_blank" rel="noopener">{{ a.ipo.registrar.name }} ↗</a>
                    }
                  </div>
                </td>
                <td>{{ a.pan_label }}<div class="text-muted text-sm">{{ a.pan_masked }}</div></td>
                <td class="num">{{ a.lots }}</td>
                <td class="num">{{ a.amount_blocked | inr }}</td>
                <td><span class="badge" [class]="a.status | tone">{{ a.status_display }}</span></td>
                <td class="num">{{ a.shares_allotted || '—' }}</td>
                <td class="num">
                  @if (a.listing_gain === null && a.expected_gain !== null) {
                    <span class="text-muted" title="From the grey market premium">{{ a.expected_gain | inr }} est.</span>
                  } @else {
                    <span [class.text-gain]="+(a.listing_gain ?? 0) > 0" [class.text-loss]="+(a.listing_gain ?? 0) < 0">{{ a.listing_gain | inr }}</span>
                  }
                </td>
                <td class="text-end">
                  <button class="btn btn-sm btn-outline-primary" (click)="editing()?.id === a.id ? editing.set(null) : open(a)">
                    {{ editing()?.id === a.id ? 'Close' : 'Update' }}
                  </button>
                </td>
              </tr>
              @if (editing()?.id === a.id) {
                <tr class="table-light">
                  <td colspan="8">
                    <div class="row g-2 align-items-end">
                      <div class="col-sm-4 col-lg-3">
                        <label class="form-label" for="newStatus">Set result</label>
                        <select id="newStatus" class="form-select form-select-sm" [(ngModel)]="newStatus">
                          @for (o of editOptions; track o.value) { <option [value]="o.value">{{ o.label }}</option> }
                        </select>
                      </div>
                      @if (newStatus === 'PARTIAL') {
                        <div class="col-sm-4 col-lg-2">
                          <label class="form-label" for="shares">Shares allotted (of {{ a.shares_applied }})</label>
                          <input id="shares" type="number" min="0" [max]="a.shares_applied" class="form-control form-control-sm" [(ngModel)]="shares" />
                        </div>
                      }
                      <div class="col-sm-4 col-lg-3">
                        <label class="form-label" for="note">Note</label>
                        <input id="note" class="form-control form-control-sm" [(ngModel)]="note" placeholder="Optional" />
                      </div>
                      <div class="col-auto d-flex gap-2">
                        <button class="btn btn-sm btn-primary" (click)="save(a)" [disabled]="busy()">Save</button>
                        <button class="btn btn-sm btn-outline-danger" (click)="remove(a)">Delete</button>
                      </div>
                    </div>
                    @if (events().length) {
                      <h6 class="mt-3 mb-2">History</h6>
                      <ul class="list-unstyled mb-0 text-sm">
                        @for (e of events(); track e.id) {
                          <li class="mb-1">
                            <span class="text-muted">{{ e.created_at | date: 'd MMM y, HH:mm' }}</span> —
                            {{ e.from_status ? label(e.from_status) + ' → ' : '' }}{{ label(e.to_status) }}
                            @if (e.source === 'REGISTRAR') { <span class="badge bg-light-primary ms-1">registrar</span> }
                            @if (e.note) { <span class="text-muted">· {{ e.note }}</span> }
                          </li>
                        }
                      </ul>
                    }
                  </td>
                </tr>
              }
            } @empty {
              <tr><td colspan="8" class="text-center text-muted py-4">No applications. Pick an <a routerLink="/ipos">IPO</a> to apply or check.</td></tr>
            }
          </tbody>
        </table>
      </div>
      @if (page(); as p) {
        @if (p.next || p.previous) {
          <div class="card-body border-top d-flex justify-content-between align-items-center">
            <button class="btn btn-sm btn-outline-secondary" [disabled]="!p.previous" (click)="load(pageNo - 1)">← Previous</button>
            <span class="text-muted text-sm">Page {{ pageNo }} · {{ p.count }} total</span>
            <button class="btn btn-sm btn-outline-secondary" [disabled]="!p.next" (click)="load(pageNo + 1)">Next →</button>
          </div>
        }
      }
    </div>
  `,
})
export class ApplicationsPage {
  private api = inject(ApiService);
  /** ?ipo=<id> from the query string, bound by withComponentInputBinding. */
  readonly ipo = input<string>();

  labels = APP_STATUS_LABELS;

  result = '';
  pan = '';
  search = '';
  typed = new Subject<void>();
  pans = signal<Pan[]>([]);

  /** Grouped the way you think about results; values are status__in lists. */
  resultFilters = [
    { label: 'All results', value: '' },
    { label: 'Awaiting result', value: 'APPLIED' },
    { label: 'Allotted (incl. partial)', value: 'ALLOTTED,PARTIAL' },
    { label: 'Not allotted', value: 'REJECTED,REFUNDED' },
    { label: 'Not applied yet', value: 'DRAFT' },
    { label: 'Withdrawn', value: 'WITHDRAWN' },
  ];

  /** What you can set by hand. Full allotment's share count is computed by the server. */
  editOptions: { value: AppStatus; label: string }[] = [
    { value: 'DRAFT', label: 'Not applied yet' },
    { value: 'APPLIED', label: 'Awaiting result' },
    { value: 'ALLOTTED', label: 'Allotted (full)' },
    { value: 'PARTIAL', label: 'Partially allotted' },
    { value: 'REJECTED', label: 'Not allotted' },
    { value: 'WITHDRAWN', label: 'Withdrawn' },
  ];
  pageNo = 1;

  page = signal<Page<Application> | null>(null);
  editing = signal<Application | null>(null);
  events = signal<StatusEvent[]>([]);
  busy = signal(false);
  error = signal('');
  checking = signal(false);
  checkResult = signal<CheckResponse | null>(null);

  newStatus: AppStatus = 'APPLIED';
  shares: number | null = null;
  note = '';

  constructor() {
    // Re-runs whenever ?ipo= changes. The router reuses this component
    // when only the query string changes, so ngOnInit alone would miss it.
    this.typed.pipe(debounceTime(250)).subscribe(() => this.load(1));
    this.api.pans().subscribe((p) => this.pans.set(p.results));
    effect(() => {
      this.ipo();
      untracked(() => this.load(1));
    });
  }

  label(s: string) {
    return this.labels[s as AppStatus] ?? s;
  }

  /** Checks this issue's PANs when filtered to one, otherwise everything pending. */
  checkAll() {
    this.checking.set(true);
    this.error.set('');
    const ipo = this.ipo();
    this.api.checkAllotments(ipo ? { ipo_id: Number(ipo) } : {}).subscribe({
      next: (r) => { this.checkResult.set(r); this.checking.set(false); this.load(this.pageNo); },
      error: (e) => { this.error.set(errorText(e)); this.checking.set(false); },
    });
  }

  load(n: number) {
    this.pageNo = n;
    this.api
      .applications({ status__in: this.result, pan: this.pan, search: this.search, ipo: this.ipo(), page: n })
      .subscribe({ next: (p) => this.page.set(p), error: (e) => this.error.set(errorText(e)) });
  }

  open(a: Application) {
    this.editing.set(a);
    this.newStatus = a.status;
    this.shares = a.shares_allotted || null;
    this.note = '';
    this.events.set([]);
    this.api.events(a.id).subscribe((ev) => this.events.set(ev));
  }

  save(a: Application) {
    this.busy.set(true);
    this.error.set('');
    const body: { status: AppStatus; shares_allotted?: number; note?: string } = { status: this.newStatus, note: this.note };
    if (this.newStatus === 'PARTIAL' && this.shares !== null) body.shares_allotted = this.shares;
    this.api.setStatus(a.id, body).subscribe({
      next: () => { this.busy.set(false); this.editing.set(null); this.load(this.pageNo); },
      error: (e) => { this.busy.set(false); this.error.set(errorText(e)); },
    });
  }

  remove(a: Application) {
    if (!confirm(`Delete the ${a.ipo.name} application for ${a.pan_label}?`)) return;
    this.api.deleteApplication(a.id).subscribe({
      next: () => { this.editing.set(null); this.load(this.pageNo); },
      error: (e) => this.error.set(errorText(e)),
    });
  }
}
