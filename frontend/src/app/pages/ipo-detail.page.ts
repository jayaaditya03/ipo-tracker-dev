import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ApiService, errorText } from '../core/api.service';
import {
  Application, BulkApplyResult, CATEGORY_LABELS, Category, CheckResponse,
  IPO_STATUS_LABELS, IPO_STATUS_TONES, Ipo, Pan,
} from '../core/models';
import { CheckResults } from '../shared/check-results';
import { InrPipe, TonePipe } from '../shared/format';

const RETAIL_LIMIT = 200000;

@Component({
  imports: [FormsModule, RouterLink, InrPipe, TonePipe, CheckResults],
  template: `
    <a routerLink="/ipos" class="link-secondary text-sm d-inline-block mb-2">← All IPOs</a>
    @if (error()) { <div class="alert alert-danger">{{ error() }}</div> }

    @if (ipo(); as i) {
      <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
        <h4 class="mb-0">{{ i.name }}</h4>
        @if (i.symbol) { <span class="text-muted">{{ i.symbol }}</span> }
        <span class="badge" [class]="ipoTones[i.status]">{{ ipoLabels[i.status] }}</span>
        <span class="badge bg-light-secondary">{{ i.board === 'SME' ? 'SME' : 'Mainboard' }}</span>
      </div>

      <div class="card">
        <div class="card-body">
          <div class="row g-3">
            @for (f of facts(); track f.label) {
              <div class="col-6 col-md-4 col-xl-2">
                <div class="text-muted text-sm">{{ f.label }}</div>
                <div class="f-w-600">{{ f.value }}</div>
              </div>
            }
            <div class="col-6 col-md-4 col-xl-2">
              <div class="text-muted text-sm">Registrar</div>
              @if (i.registrar.status_check_url) {
                <a class="f-w-600" [href]="i.registrar.status_check_url" target="_blank" rel="noopener">{{ i.registrar.name }} ↗</a>
              } @else {
                <div class="f-w-600">{{ i.registrar.name }}</div>
              }
            </div>
          </div>
          @if (i.dates_estimated) {
            <p class="text-muted text-sm mb-0 mt-3">
              * Estimated from the SEBI T+3 timeline. NSE doesn't publish these dates.
            </p>
          }
        </div>
      </div>

      <div class="row">
        @if (mine().length) {
          <div class="col-xl-6">
            <div class="card">
              <div class="card-header d-flex justify-content-between align-items-center">
                <h5 class="mb-0">Your applications</h5>
                <a routerLink="/applications" [queryParams]="{ ipo: i.id }" class="link-primary text-sm">Manage →</a>
              </div>
              <div class="table-responsive">
                <table class="table table-hover mb-0">
                  <thead><tr><th>Applicant</th><th class="num">Lots</th><th class="num">Blocked</th><th>Result</th></tr></thead>
                  <tbody>
                    @for (a of mine(); track a.id) {
                      <tr>
                        <td>{{ a.pan_label }} <span class="text-muted text-sm">{{ a.pan_masked }}</span></td>
                        <td class="num">{{ a.lots }}</td>
                        <td class="num">{{ a.amount_blocked | inr }}</td>
                        <td><span class="badge" [class]="a.status | tone">{{ a.status_display }}</span></td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
              @if (pending()) {
                <div class="card-body border-top">
                  <button class="btn btn-primary" (click)="checkAllotment()" [disabled]="checking()">
                    {{ checking() ? 'Asking ' + i.registrar.name + '…' : 'Check allotment for ' + pending() + ' PAN(s)' }}
                  </button>
                  <app-check-results [data]="checkResult()" />
                </div>
              }
            </div>
          </div>
        }

        <div [class]="mine().length ? 'col-xl-6' : 'col-12'">
          @if (canApply()) {
            <div class="card">
              <div class="card-header"><h5 class="mb-0">Apply across PANs</h5></div>
              <div class="card-body">
                @if (result(); as r) {
                  <div class="alert alert-success">
                    Recorded {{ r.summary.created }} of {{ r.summary.requested }} application(s).
                    @for (s of r.skipped; track s.pan_id) { <div>Skipped {{ s.pan_label }}: {{ s.reason }}</div> }
                  </div>
                }
                @if (availablePans().length) {
                  <div class="row g-2 mb-2">
                    <div class="col-sm-6">
                      <label class="form-label" for="category">Category</label>
                      <select id="category" class="form-select" [(ngModel)]="category">
                        @for (c of categories; track c) { <option [value]="c">{{ categoryLabels[c] }}</option> }
                      </select>
                    </div>
                    <div class="col-sm-6">
                      <label class="form-label" for="lots">Lots per PAN</label>
                      <input id="lots" type="number" min="1" class="form-control" [(ngModel)]="lots" />
                    </div>
                  </div>
                  <p class="text-muted text-sm">
                    {{ lots * (i.lot_size ?? 0) }} shares · {{ perPan() | inr }} per PAN
                    @if (overRetail()) { <span class="text-danger"> — over the ₹2,00,000 retail limit</span> }
                  </p>
                  <div class="pan-picker mb-3">
                    @for (p of availablePans(); track p.id) {
                      <div class="form-check">
                        <input class="form-check-input" type="checkbox" [id]="'apply-' + p.id" [checked]="selected().has(p.id)" (change)="toggle(p.id)" />
                        <label class="form-check-label" [for]="'apply-' + p.id">{{ p.label }} <span class="text-muted">{{ p.pan_masked }}</span></label>
                      </div>
                    }
                  </div>
                  <div class="form-check mb-3">
                    <input class="form-check-input" type="checkbox" id="markApplied" [(ngModel)]="markApplied" />
                    <label class="form-check-label" for="markApplied">Already submitted with my broker</label>
                  </div>
                  <button class="btn btn-primary" (click)="apply()" [disabled]="busy() || !selected().size || overRetail()">
                    {{ busy() ? 'Saving…' : 'Apply with ' + selected().size + ' PAN(s)' }}
                  </button>
                } @else if (pans().length) {
                  <p class="text-muted mb-0">Every active PAN already has an application for this issue.</p>
                } @else {
                  <p class="text-muted mb-0">You need a PAN first. <a routerLink="/pans">Add one</a>.</p>
                }
              </div>
            </div>
          } @else if (i.status !== 'WITHDRAWN') {
            <div class="card">
              <div class="card-header"><h5 class="mb-0">Check allotment for your PANs</h5></div>
              <div class="card-body">
                @if (pans().length) {
                  <p class="text-muted text-sm">
                    Pick the PANs that applied. Each one is looked up with {{ i.registrar.name }}. PANs the registrar confirms
                    are saved to your applications; any it has no record of are left out.
                  </p>
                  <div class="pan-picker mb-3">
                    @for (p of pans(); track p.id) {
                      <div class="form-check">
                        <input class="form-check-input" type="checkbox" [id]="'check-' + p.id" [checked]="checkSel().has(p.id)" (change)="toggleCheck(p.id)" />
                        <label class="form-check-label" [for]="'check-' + p.id">{{ p.label }} <span class="text-muted">{{ p.pan_masked }}</span></label>
                      </div>
                    }
                  </div>
                  <button class="btn btn-primary" (click)="checkPans()" [disabled]="checking() || !checkSel().size">
                    {{ checking() ? 'Asking ' + i.registrar.name + '…' : 'Check ' + checkSel().size + ' PAN(s)' }}
                  </button>
                  <app-check-results [data]="panCheck()" />
                } @else {
                  <p class="text-muted mb-0">You need a PAN first. <a routerLink="/pans">Add one</a>.</p>
                }
              </div>
            </div>
          }
        </div>
      </div>
    }
  `,
})
export class IpoDetailPage implements OnInit {
  private api = inject(ApiService);
  private inr = new InrPipe();
  private dates = new DatePipe('en-US');
  private num = new DecimalPipe('en-US');
  readonly id = input.required<string>();

  categories = Object.keys(CATEGORY_LABELS) as Category[];
  categoryLabels = CATEGORY_LABELS;
  ipoLabels = IPO_STATUS_LABELS;
  ipoTones = IPO_STATUS_TONES;

  ipo = signal<Ipo | null>(null);
  pans = signal<Pan[]>([]);
  mine = signal<Application[]>([]);
  selected = signal<Set<number>>(new Set());
  checkSel = signal<Set<number>>(new Set());
  result = signal<BulkApplyResult | null>(null);
  checkResult = signal<CheckResponse | null>(null);
  panCheck = signal<CheckResponse | null>(null);
  busy = signal(false);
  checking = signal(false);
  error = signal('');

  category: Category = 'RETAIL';
  lots = 1;
  markApplied = true;

  pending = computed(() => this.mine().filter((a) => a.status === 'APPLIED').length);
  canApply = computed(() => {
    const s = this.ipo()?.status;
    return s === 'OPEN' || s === 'UPCOMING';
  });
  availablePans = computed(() => {
    const used = new Set(this.mine().map((a) => a.pan_id));
    return this.pans().filter((p) => p.is_active && !used.has(p.id));
  });

  facts = computed(() => {
    const i = this.ipo();
    if (!i) return [];
    const d = (v?: string | null) => (v ? this.dates.transform(v, 'd MMM y') : '—');
    const est = i.dates_estimated ? ' *' : '';
    const facts = [
      { label: 'Price band', value: `${this.inr.transform(i.price_band_low)} – ${this.inr.transform(i.price_band_high)}` },
      { label: 'Lot size', value: i.lot_size ? `${i.lot_size} shares` : '—' },
      { label: 'Min. amount', value: this.inr.transform(i.lot_amount) },
      { label: 'Bidding', value: `${d(i.open_date)} – ${d(i.close_date)}` },
      { label: 'Allotment' + est, value: d(i.allotment_date) },
      { label: 'Refund' + est, value: d(i.refund_date) },
      { label: 'Listing' + est, value: d(i.listing_date) },
      { label: 'GMP', value: this.inr.transform(i.gmp) },
      { label: 'Issue size', value: i.issue_size_cr ? `₹${this.num.transform(i.issue_size_cr, '1.0-2')} Cr` : '—' },
    ];
    if (i.listing_price) {
      facts.push({ label: 'Listing price',
        value: `${this.inr.transform(i.listing_price)} (${this.num.transform(i.listing_gain_pct, '1.1-1')}%)` });
    }
    return facts;
  });

  perPan() {
    const i = this.ipo();
    return this.lots * (i?.lot_size ?? 0) * Number(i?.cutoff_price ?? 0);
  }
  overRetail() {
    return this.category === 'RETAIL' && this.perPan() > RETAIL_LIMIT;
  }

  ngOnInit() {
    this.api.ipo(Number(this.id())).subscribe({ next: (i) => this.ipo.set(i), error: (e) => this.error.set(errorText(e)) });
    this.api.pans({ is_active: true }).subscribe((p) => {
      this.pans.set(p.results);
      this.checkSel.set(new Set(p.results.map((x) => x.id)));
    });
    this.loadMine();
  }

  loadMine() {
    this.api.applications({ ipo: this.id(), page_size: 100 }).subscribe((p) => this.mine.set(p.results));
  }

  toggle(id: number) {
    this.selected.set(flip(this.selected(), id));
  }

  toggleCheck(id: number) {
    this.checkSel.set(flip(this.checkSel(), id));
  }

  apply() {
    this.busy.set(true);
    this.error.set('');
    this.api
      .bulkApply({
        ipo_id: Number(this.id()), pan_ids: [...this.selected()],
        category: this.category, lots: this.lots, mark_applied: this.markApplied,
      })
      .subscribe({
        next: (r) => { this.result.set(r); this.selected.set(new Set()); this.busy.set(false); this.loadMine(); },
        error: (e) => { this.error.set(errorText(e)); this.busy.set(false); },
      });
  }

  checkAllotment() {
    this.checking.set(true);
    this.error.set('');
    this.api.checkAllotments({ ipo_id: Number(this.id()) }).subscribe({
      next: (r) => { this.checkResult.set(r); this.checking.set(false); this.loadMine(); },
      error: (e) => { this.error.set(errorText(e)); this.checking.set(false); },
    });
  }

  checkPans() {
    this.checking.set(true);
    this.error.set('');
    this.api.checkPans(Number(this.id()), [...this.checkSel()]).subscribe({
      next: (r) => { this.panCheck.set(r); this.checking.set(false); this.loadMine(); },
      error: (e) => { this.error.set(errorText(e)); this.checking.set(false); },
    });
  }
}

function flip(set: Set<number>, id: number): Set<number> {
  const next = new Set(set);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}
