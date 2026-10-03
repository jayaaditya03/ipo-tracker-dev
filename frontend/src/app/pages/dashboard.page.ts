import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService, errorText } from '../core/api.service';
import { DashboardSummary, Ipo } from '../core/models';
import { InrPipe } from '../shared/format';

@Component({
  imports: [RouterLink, InrPipe, DatePipe],
  template: `
    <h1>Dashboard</h1>
    @if (error()) { <div class="error">{{ error() }}</div> }

    @if (s(); as s) {
      <div class="grid">
        <div class="card stat"><div class="label">Applications</div><div class="value">{{ s.applications }}</div></div>
        <div class="card stat"><div class="label">Awaiting result</div><div class="value">{{ s.pending }}</div></div>
        <div class="card stat"><div class="label">Allotted</div><div class="value">{{ s.allotted }}</div></div>
        <div class="card stat"><div class="label">Hit rate</div><div class="value">{{ s.hit_rate }}%</div></div>
        <div class="card stat"><div class="label">Money blocked</div><div class="value">{{ s.blocked | inr }}</div></div>
        <div class="card stat"><div class="label">Invested (allotted)</div><div class="value">{{ s.invested | inr }}</div></div>
        <div class="card stat">
          <div class="label">Listing gain</div>
          <div class="value" [class.pos]="+s.realised_gain > 0" [class.neg]="+s.realised_gain < 0">{{ s.realised_gain | inr }}</div>
        </div>
      </div>

      <div class="card">
        <h2>By PAN</h2>
        @if (s.by_pan.length) {
          <div class="table-wrap"><table>
            <thead><tr><th>Applicant</th><th class="num">Applied</th><th class="num">Allotted</th><th class="num">Hit rate</th></tr></thead>
            <tbody>
              @for (p of s.by_pan; track p.pan__id) {
                <tr>
                  <td>{{ p.pan__label }}</td>
                  <td class="num">{{ p.applications }}</td>
                  <td class="num">{{ p.allotted }}</td>
                  <td class="num">{{ p.applications ? ((p.allotted / p.applications) * 100).toFixed(0) : 0 }}%</td>
                </tr>
              }
            </tbody>
          </table></div>
        } @else {
          <p class="empty">No applications yet. <a routerLink="/pans">Add a PAN</a>, then apply to an <a routerLink="/ipos">open IPO</a>.</p>
        }
      </div>
    }

    <div class="card">
      <h2>Open for bidding today</h2>
      @if (open().length) {
        <div class="table-wrap"><table>
          <thead><tr><th>Issue</th><th>Board</th><th>Closes</th><th class="num">Price</th><th class="num">Min. amount</th></tr></thead>
          <tbody>
            @for (i of open(); track i.id) {
              <tr>
                <td><a [routerLink]="['/ipos', i.id]">{{ i.name }}</a></td>
                <td>{{ i.board === 'SME' ? 'SME' : 'Main' }}</td>
                <td>{{ i.close_date | date: 'd MMM' }}</td>
                <td class="num">{{ i.cutoff_price | inr }}</td>
                <td class="num">{{ i.lot_amount | inr }}</td>
              </tr>
            }
          </tbody>
        </table></div>
      } @else {
        <p class="empty">Nothing open today.</p>
      }
    </div>
  `,
})
export class DashboardPage {
  private api = inject(ApiService);
  s = signal<DashboardSummary | null>(null);
  open = signal<Ipo[]>([]);
  error = signal('');

  constructor() {
    this.api.summary().subscribe({ next: (s) => this.s.set(s), error: (e) => this.error.set(errorText(e)) });
    this.api.openNow().subscribe((o) => this.open.set(o));
  }
}
