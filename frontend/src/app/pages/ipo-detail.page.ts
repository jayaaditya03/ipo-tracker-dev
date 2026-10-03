import { DatePipe, DecimalPipe, TitleCasePipe } from '@angular/common';
import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ApiService, errorText } from '../core/api.service';
import { Application, BulkApplyResult, CATEGORY_LABELS, Category, CheckResponse, Ipo, Pan } from '../core/models';
import { CheckResults } from '../shared/check-results';
import { InrPipe, TonePipe } from '../shared/format';

const RETAIL_LIMIT = 200000;

@Component({
  imports: [FormsModule, RouterLink, DatePipe, DecimalPipe, TitleCasePipe, InrPipe, TonePipe, CheckResults],
  template: `
    <p><a routerLink="/ipos">← All IPOs</a></p>
    @if (error()) { <div class="error">{{ error() }}</div> }

    @if (ipo(); as i) {
      <div class="page-head">
        <h1>{{ i.name }} @if (i.symbol) { <span class="muted">· {{ i.symbol }}</span> }</h1>
        <span class="badge" [class]="i.status | tone">{{ i.status | titlecase }}</span>
      </div>

      <div class="card">
        <dl class="facts">
          <div><dt>Board</dt><dd>{{ i.board === 'SME' ? 'SME' : 'Mainboard' }}</dd></div>
          <div><dt>Price band</dt><dd>{{ i.price_band_low | inr }} – {{ i.price_band_high | inr }}</dd></div>
          <div><dt>Lot size</dt><dd>{{ i.lot_size ?? '—' }} shares</dd></div>
          <div><dt>Min. amount</dt><dd>{{ i.lot_amount | inr }}</dd></div>
          <div><dt>Issue size</dt><dd>{{ i.issue_size_cr ? (i.issue_size_cr | number: '1.0-2') + ' Cr' : '—' }}</dd></div>
          <div><dt>GMP</dt><dd>{{ i.gmp | inr }}</dd></div>
          <div><dt>Open</dt><dd>{{ (i.open_date | date: 'd MMM y') ?? '—' }}</dd></div>
          <div><dt>Close</dt><dd>{{ (i.close_date | date: 'd MMM y') ?? '—' }}</dd></div>
          <div><dt>Allotment @if (i.dates_estimated) { <span title="Estimated from the SEBI T+3 timeline">(est.)</span> }</dt><dd>{{ (i.allotment_date | date: 'd MMM y') ?? '—' }}</dd></div>
          <div><dt>Refund @if (i.dates_estimated) { <span title="Estimated from the SEBI T+3 timeline">(est.)</span> }</dt><dd>{{ (i.refund_date | date: 'd MMM y') ?? '—' }}</dd></div>
          <div><dt>Listing @if (i.dates_estimated) { <span title="Estimated from the SEBI T+3 timeline">(est.)</span> }</dt><dd>{{ (i.listing_date | date: 'd MMM y') ?? '—' }}</dd></div>
          @if (i.listing_price) {
            <div><dt>Listing price</dt><dd>{{ i.listing_price | inr }}
              <span [class.pos]="+i.listing_gain_pct! > 0" [class.neg]="+i.listing_gain_pct! < 0">({{ i.listing_gain_pct | number: '1.1-1' }}%)</span></dd></div>
          }
          <div><dt>Registrar</dt><dd>
            @if (i.registrar.status_check_url) {
              <a [href]="i.registrar.status_check_url" target="_blank" rel="noopener">{{ i.registrar.name }} ↗</a>
            } @else { {{ i.registrar.name }} }
          </dd></div>
        </dl>
      </div>

      @if (mine().length) {
        <div class="card">
          <h2>Your applications</h2>
          <div class="table-wrap"><table>
            <thead><tr><th>Applicant</th><th>Category</th><th class="num">Lots</th><th class="num">Blocked</th><th>Status</th></tr></thead>
            <tbody>
              @for (a of mine(); track a.id) {
                <tr>
                  <td>{{ a.pan_label }} <span class="muted">{{ a.pan_masked }}</span></td>
                  <td>{{ categoryLabels[a.category] }}</td>
                  <td class="num">{{ a.lots }}</td>
                  <td class="num">{{ a.amount_blocked | inr }}</td>
                  <td><span class="badge" [class]="a.status | tone">{{ a.status_display }}</span></td>
                </tr>
              }
            </tbody>
          </table></div>
          <div class="inline">
            @if (pending()) {
              <button class="primary" (click)="checkAllotment()" [disabled]="checking()">
                {{ checking() ? 'Asking ' + i.registrar.name + '…' : 'Check allotment for ' + pending() + ' PAN(s)' }}
              </button>
            }
            <a routerLink="/applications" [queryParams]="{ ipo: i.id }">Manage on the Applications page →</a>
          </div>
          <app-check-results [data]="checkResult()" />
        </div>
      }

      @if (canApply()) {
        <div class="card">
          <h2>Apply across PANs</h2>
          @if (result(); as r) {
            <div class="notice">
              Recorded {{ r.summary.created }} of {{ r.summary.requested }} application(s).
              @for (s of r.skipped; track s.pan_id) { <div>Skipped {{ s.pan_label }}: {{ s.reason }}</div> }
            </div>
          }
          @if (availablePans().length) {
            <div class="inline">
              <label>Category
                <select [(ngModel)]="category">
                  @for (c of categories; track c) { <option [value]="c">{{ categoryLabels[c] }}</option> }
                </select>
              </label>
              <label>Lots per PAN <input type="number" min="1" [(ngModel)]="lots" /></label>
              <label><input type="checkbox" [(ngModel)]="markApplied" /> Already submitted with broker</label>
            </div>
            <p class="muted">
              {{ lots * (i.lot_size ?? 0) }} shares · {{ perPan() | inr }} per PAN
              @if (overRetail()) { <span class="neg"> — exceeds the ₹2,00,000 retail limit</span> }
            </p>
            @for (p of availablePans(); track p.id) {
              <label><input type="checkbox" [checked]="selected().has(p.id)" (change)="toggle(p.id)" />
                {{ p.label }} <span class="muted">{{ p.pan_masked }}</span></label>
            }
            <button class="primary" (click)="apply()" [disabled]="busy() || !selected().size || overRetail()">
              {{ busy() ? 'Saving…' : 'Apply with ' + selected().size + ' PAN(s)' }}
            </button>
          } @else if (pans().length) {
            <p class="muted">Every active PAN already has an application for this issue.</p>
          } @else {
            <p class="muted">You need a PAN first. <a routerLink="/pans">Add one</a>.</p>
          }
        </div>
      }
    }
  `,
})
export class IpoDetailPage implements OnInit {
  private api = inject(ApiService);
  readonly id = input.required<string>();

  categories = Object.keys(CATEGORY_LABELS) as Category[];
  categoryLabels = CATEGORY_LABELS;

  ipo = signal<Ipo | null>(null);
  pans = signal<Pan[]>([]);
  mine = signal<Application[]>([]);
  selected = signal<Set<number>>(new Set());
  result = signal<BulkApplyResult | null>(null);
  busy = signal(false);
  error = signal('');
  checking = signal(false);
  checkResult = signal<CheckResponse | null>(null);
  pending = computed(() => this.mine().filter((a) => a.status === 'APPLIED').length);

  category: Category = 'RETAIL';
  lots = 1;
  markApplied = true;

  canApply = computed(() => {
    const s = this.ipo()?.status;
    return s === 'OPEN' || s === 'UPCOMING';
  });
  availablePans = computed(() => {
    const used = new Set(this.mine().map((a) => a.pan_id));
    return this.pans().filter((p) => p.is_active && !used.has(p.id));
  });

  perPan() {
    const i = this.ipo();
    return this.lots * (i?.lot_size ?? 0) * Number(i?.cutoff_price ?? 0);
  }
  overRetail() {
    return this.category === 'RETAIL' && this.perPan() > RETAIL_LIMIT;
  }

  ngOnInit() {
    const id = Number(this.id());
    this.api.ipo(id).subscribe({ next: (i) => this.ipo.set(i), error: (e) => this.error.set(errorText(e)) });
    this.api.pans({ is_active: true }).subscribe((p) => this.pans.set(p.results));
    this.loadMine();
  }

  checkAllotment() {
    this.checking.set(true);
    this.error.set('');
    this.api.checkAllotments({ ipo_id: Number(this.id()) }).subscribe({
      next: (r) => { this.checkResult.set(r); this.checking.set(false); this.loadMine(); },
      error: (e) => { this.error.set(errorText(e)); this.checking.set(false); },
    });
  }

  loadMine() {
    this.api.applications({ ipo: this.id(), page_size: 100 }).subscribe((p) => this.mine.set(p.results));
  }

  toggle(id: number) {
    const next = new Set(this.selected());
    next.has(id) ? next.delete(id) : next.add(id);
    this.selected.set(next);
  }

  apply() {
    this.busy.set(true);
    this.error.set('');
    this.api
      .bulkApply({
        ipo_id: Number(this.id()),
        pan_ids: [...this.selected()],
        category: this.category,
        lots: this.lots,
        mark_applied: this.markApplied,
      })
      .subscribe({
        next: (r) => {
          this.result.set(r);
          this.selected.set(new Set());
          this.busy.set(false);
          this.loadMine();
        },
        error: (e) => { this.error.set(errorText(e)); this.busy.set(false); },
      });
  }
}
