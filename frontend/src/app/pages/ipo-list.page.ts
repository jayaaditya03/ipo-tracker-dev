import { DatePipe, TitleCasePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Subject, debounceTime } from 'rxjs';

import { ApiService, errorText } from '../core/api.service';
import { Ipo } from '../core/models';
import { InrPipe, TonePipe } from '../shared/format';

const STATUSES = ['', 'OPEN', 'UPCOMING', 'CLOSED', 'ALLOTTED', 'LISTED'] as const;

@Component({
  imports: [FormsModule, RouterLink, DatePipe, TitleCasePipe, InrPipe, TonePipe],
  template: `
    <div class="page-head">
      <h1>IPOs</h1>
      <div class="inline">
        <label>Search <input [(ngModel)]="search" (ngModelChange)="typed.next()" placeholder="Name or symbol" /></label>
        <label>Board
          <select [(ngModel)]="board" (ngModelChange)="load()">
            <option value="">All</option><option value="MAINBOARD">Mainboard</option><option value="SME">SME</option>
          </select>
        </label>
      </div>
    </div>

    <div class="tabs">
      @for (s of statuses; track s) {
        <button [class.on]="status === s" (click)="status = s; load()">{{ s ? (s | titlecase) : 'All' }}</button>
      }
    </div>

    @if (error()) { <div class="error">{{ error() }}</div> }

    <div class="card table-wrap">
      <table>
        <thead><tr>
          <th>Issue</th><th>Status</th><th>Board</th><th>Dates</th>
          <th class="num">Price band</th><th class="num">Lot</th><th class="num">Min. amount</th><th class="num">GMP</th><th></th>
        </tr></thead>
        <tbody>
          @for (i of ipos(); track i.id) {
            <tr>
              <td><a [routerLink]="['/ipos', i.id]">{{ i.name }}</a><div class="muted">{{ i.registrar.name }}</div></td>
              <td><span class="badge" [class]="i.status | tone">{{ i.status | titlecase }}</span></td>
              <td>{{ i.board === 'SME' ? 'SME' : 'Main' }}</td>
              <td>{{ i.open_date | date: 'd MMM' }} – {{ i.close_date | date: 'd MMM' }}</td>
              <td class="num">{{ i.price_band_low | inr }}–{{ i.price_band_high | inr }}</td>
              <td class="num">{{ i.lot_size ?? '—' }}</td>
              <td class="num">{{ i.lot_amount | inr }}</td>
              <td class="num" [class.pos]="+(i.gmp ?? 0) > 0" [class.neg]="+(i.gmp ?? 0) < 0">{{ i.gmp | inr }}</td>
              <td>@if (i.status === 'OPEN' || i.status === 'UPCOMING') { <a [routerLink]="['/ipos', i.id]">Apply</a> } @else if (i.status !== 'WITHDRAWN') { <a [routerLink]="['/ipos', i.id]">Check</a> }</td>
            </tr>
          } @empty {
            <tr><td colspan="9" class="empty">{{ loading() ? 'Loading…' : 'No issues match.' }}</td></tr>
          }
        </tbody>
      </table>
    </div>
  `,
})
export class IpoListPage {
  private api = inject(ApiService);

  statuses = STATUSES;
  status: string = '';
  board = '';
  search = '';
  typed = new Subject<void>();

  ipos = signal<Ipo[]>([]);
  loading = signal(true);
  error = signal('');

  constructor() {
    this.typed.pipe(debounceTime(250)).subscribe(() => this.load());
    this.load();
  }

  load() {
    this.loading.set(true);
    this.api.ipos({ status: this.status, board: this.board, search: this.search, page_size: 100 }).subscribe({
      next: (p) => { this.ipos.set(p.results); this.loading.set(false); },
      error: (e) => { this.error.set(errorText(e)); this.loading.set(false); },
    });
  }
}
