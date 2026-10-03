import { DatePipe } from '@angular/common';
import { Component, effect, inject, input, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ApiService, errorText } from '../core/api.service';
import { APP_STATUS_LABELS, AppStatus, Application, Page, StatusEvent } from '../core/models';
import { InrPipe, TonePipe } from '../shared/format';

@Component({
  imports: [FormsModule, RouterLink, DatePipe, InrPipe, TonePipe],
  template: `
    <div class="page-head">
      <h1>Applications</h1>
      <div class="inline">
        <label>Search <input [(ngModel)]="search" (keyup.enter)="load(1)" placeholder="IPO or applicant" /></label>
        <label>Status
          <select [(ngModel)]="status" (ngModelChange)="load(1)">
            <option value="">All</option>
            @for (s of statuses; track s) { <option [value]="s">{{ labels[s] }}</option> }
          </select>
        </label>
      </div>
    </div>
    @if (ipo()) { <p class="muted">Filtered to one issue. <a routerLink="/applications">Show all</a></p> }
    @if (error()) { <div class="error">{{ error() }}</div> }

    <div class="card table-wrap">
      <table>
        <thead><tr>
          <th>IPO</th><th>Applicant</th><th class="num">Lots</th><th class="num">Blocked</th>
          <th>Status</th><th class="num">Allotted</th><th class="num">Gain</th><th></th>
        </tr></thead>
        <tbody>
          @for (a of page()?.results; track a.id) {
            <tr>
              <td><a [routerLink]="['/ipos', a.ipo.id]">{{ a.ipo.name }}</a>
                <div class="muted">Allotment {{ (a.ipo.allotment_date | date: 'd MMM') ?? '—' }}
                  @if (a.ipo.registrar.status_check_url) {
                    · <a [href]="a.ipo.registrar.status_check_url" target="_blank" rel="noopener">check ↗</a>
                  }
                </div>
              </td>
              <td>{{ a.pan_label }}<div class="muted">{{ a.pan_masked }}</div></td>
              <td class="num">{{ a.lots }}</td>
              <td class="num">{{ a.amount_blocked | inr }}</td>
              <td><span class="badge" [class]="a.status | tone">{{ a.status_display }}</span></td>
              <td class="num">{{ a.shares_allotted || '—' }}</td>
              <td class="num" [class.pos]="+(a.listing_gain ?? 0) > 0" [class.neg]="+(a.listing_gain ?? 0) < 0">{{ a.listing_gain | inr }}</td>
              <td><button class="link" (click)="open(a)">Update</button></td>
            </tr>
            @if (editing()?.id === a.id) {
              <tr><td colspan="8">
                <div class="inline">
                  <label>New status
                    <select [(ngModel)]="newStatus">
                      @for (s of statuses; track s) { <option [value]="s">{{ labels[s] }}</option> }
                    </select>
                  </label>
                  @if (newStatus === 'PARTIAL' || newStatus === 'ALLOTTED') {
                    <label>Shares allotted (of {{ a.shares_applied }})
                      <input type="number" min="0" [max]="a.shares_applied" [(ngModel)]="shares" /></label>
                  }
                  <label>Note <input [(ngModel)]="note" placeholder="Optional" /></label>
                  <button class="primary" (click)="save(a)" [disabled]="busy()">Save</button>
                  <button (click)="editing.set(null)">Cancel</button>
                  <button class="danger" (click)="remove(a)">Delete</button>
                </div>
                @if (events().length) {
                  <h2>History</h2>
                  <ul>
                    @for (e of events(); track e.id) {
                      <li>{{ e.created_at | date: 'd MMM y, HH:mm' }} —
                        {{ e.from_status ? label(e.from_status) + ' → ' : '' }}{{ label(e.to_status) }}
                        @if (e.note) { <span class="muted">· {{ e.note }}</span> }</li>
                    }
                  </ul>
                }
              </td></tr>
            }
          } @empty {
            <tr><td colspan="8" class="empty">No applications. Pick an <a routerLink="/ipos">IPO</a> to apply.</td></tr>
          }
        </tbody>
      </table>
    </div>

    @if (page(); as p) {
      @if (p.next || p.previous) {
        <div class="inline">
          <button [disabled]="!p.previous" (click)="load(pageNo - 1)">← Previous</button>
          <span class="muted">Page {{ pageNo }} · {{ p.count }} total</span>
          <button [disabled]="!p.next" (click)="load(pageNo + 1)">Next →</button>
        </div>
      }
    }
  `,
})
export class ApplicationsPage {
  private api = inject(ApiService);
  /** ?ipo=<id> from the query string, bound by withComponentInputBinding. */
  readonly ipo = input<string>();

  statuses = Object.keys(APP_STATUS_LABELS) as AppStatus[];
  labels = APP_STATUS_LABELS;

  status = '';
  search = '';
  pageNo = 1;

  page = signal<Page<Application> | null>(null);
  editing = signal<Application | null>(null);
  events = signal<StatusEvent[]>([]);
  busy = signal(false);
  error = signal('');

  newStatus: AppStatus = 'APPLIED';
  shares: number | null = null;
  note = '';

  constructor() {
    // Re-runs whenever ?ipo= changes. The router reuses this component
    // when only the query string changes, so ngOnInit alone would miss it.
    effect(() => {
      this.ipo();
      untracked(() => this.load(1));
    });
  }

  label(s: string) {
    return this.labels[s as AppStatus] ?? s;
  }

  load(n: number) {
    this.pageNo = n;
    this.api
      .applications({ status: this.status, search: this.search, ipo: this.ipo(), page: n })
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
    if (this.newStatus === 'ALLOTTED' && this.shares) body.shares_allotted = this.shares;
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
