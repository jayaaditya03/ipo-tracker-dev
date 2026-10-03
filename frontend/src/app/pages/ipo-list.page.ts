import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Subject, debounceTime } from 'rxjs';

import { ApiService, errorText } from '../core/api.service';
import { IPO_STATUS_LABELS, IPO_STATUS_TONES, Ipo, IpoStatus } from '../core/models';
import { InrPipe } from '../shared/format';

const STATUSES: ('' | IpoStatus)[] = ['', 'OPEN', 'UPCOMING', 'CLOSED', 'ALLOTTED', 'LISTED'];

@Component({
  imports: [FormsModule, RouterLink, DatePipe, InrPipe],
  template: `
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
      <h4 class="mb-0">IPOs @if (!loading()) { <span class="text-muted f-w-400 f-16">· {{ total() }}</span> }</h4>
      <div class="d-flex flex-wrap gap-2">
        <input class="form-control form-control-sm" style="width: 220px" [(ngModel)]="search" (ngModelChange)="typed.next()"
          placeholder="Search name or symbol" aria-label="Search" />
        <select class="form-select form-select-sm" style="width: 150px" [(ngModel)]="board" (ngModelChange)="load()" aria-label="Board">
          <option value="">All boards</option>
          <option value="MAINBOARD">Mainboard</option>
          <option value="SME">SME</option>
        </select>
      </div>
    </div>

    <div class="d-flex flex-wrap gap-2 mb-3 filter-pills">
      @for (s of statuses; track s) {
        <button type="button" class="btn btn-sm" [class.btn-primary]="status === s" [class.btn-outline-secondary]="status !== s"
          (click)="status = s; load()">{{ s ? labels[s] : 'All' }}</button>
      }
    </div>

    @if (error()) { <div class="alert alert-danger">{{ error() }}</div> }

    <div class="card">
      <div class="table-responsive">
        <table class="table table-hover mb-0">
          <thead>
            <tr>
              <th>Issue</th><th>Stage</th><th>Board</th><th>Bidding</th>
              <th class="num">Price band</th><th class="num">Lot</th><th class="num">Min. amount</th><th></th>
            </tr>
          </thead>
          <tbody>
            @for (i of ipos(); track i.id) {
              <tr>
                <td>
                  <a [routerLink]="['/ipos', i.id]" class="f-w-600">{{ i.name }}</a>
                  <div class="text-muted text-sm">{{ i.symbol }} · {{ i.registrar.name }}</div>
                </td>
                <td><span class="badge" [class]="tones[i.status]">{{ labels[i.status] }}</span></td>
                <td>{{ i.board === 'SME' ? 'SME' : 'Main' }}</td>
                <td class="text-nowrap">{{ i.open_date | date: 'd MMM' }} – {{ i.close_date | date: 'd MMM' }}</td>
                <td class="num">{{ i.price_band_low | inr }}–{{ i.price_band_high | inr }}</td>
                <td class="num">{{ i.lot_size ?? '—' }}</td>
                <td class="num">{{ i.lot_amount | inr }}</td>
                <td class="text-end">
                  @if (i.status === 'OPEN' || i.status === 'UPCOMING') {
                    <a [routerLink]="['/ipos', i.id]" class="btn btn-sm btn-primary">Apply</a>
                  } @else if (i.status !== 'WITHDRAWN') {
                    <a [routerLink]="['/ipos', i.id]" class="btn btn-sm btn-light-primary">Check</a>
                  }
                </td>
              </tr>
            } @empty {
              <tr><td colspan="8" class="text-center text-muted py-4">{{ loading() ? 'Loading…' : 'No issues match.' }}</td></tr>
            }
          </tbody>
        </table>
      </div>
    </div>
  `,
})
export class IpoListPage {
  private api = inject(ApiService);

  statuses = STATUSES;
  labels = IPO_STATUS_LABELS;
  tones = IPO_STATUS_TONES;
  status: '' | IpoStatus = '';
  board = '';
  search = '';
  typed = new Subject<void>();

  ipos = signal<Ipo[]>([]);
  total = signal(0);
  loading = signal(true);
  error = signal('');

  constructor() {
    this.typed.pipe(debounceTime(250)).subscribe(() => this.load());
    this.load();
  }

  load() {
    this.loading.set(true);
    this.api.ipos({ status: this.status, board: this.board, search: this.search, page_size: 100 }).subscribe({
      next: (p) => { this.ipos.set(p.results); this.total.set(p.count); this.loading.set(false); },
      error: (e) => { this.error.set(errorText(e)); this.loading.set(false); },
    });
  }
}
