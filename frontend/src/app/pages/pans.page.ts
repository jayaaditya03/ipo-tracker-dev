import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService, errorText } from '../core/api.service';
import { Pan } from '../core/models';

const PAN_RE = /^[A-Z]{5}[0-9]{4}[A-Z]$/;

@Component({
  imports: [FormsModule],
  template: `
    <h1>PANs</h1>
    <p class="muted">Each family member you apply for. PANs are encrypted on the server and only ever shown masked.</p>
    @if (error()) { <div class="error">{{ error() }}</div> }

    <div class="card">
      <h2>Add a PAN</h2>
      <form class="inline" (ngSubmit)="add()">
        <label>Label <input name="label" [(ngModel)]="form.label" placeholder="Self, Mother…" required /></label>
        <label>PAN <input name="pan" [(ngModel)]="form.pan" maxlength="10" placeholder="ABCDE1234F"
          (ngModelChange)="form.pan = $event.toUpperCase()" required /></label>
        <label>Demat / DP ID <input name="dp_id" [(ngModel)]="form.dp_id" placeholder="Optional" /></label>
        <button class="primary" type="submit" [disabled]="busy() || !valid()">Add</button>
      </form>
      @if (form.pan && !valid()) { <p class="muted">Format: five letters, four digits, one letter.</p> }
    </div>

    <div class="card table-wrap">
      <table>
        <thead><tr><th>Label</th><th>PAN</th><th>DP ID</th><th class="num">Applications</th><th>Active</th><th></th></tr></thead>
        <tbody>
          @for (p of pans(); track p.id) {
            <tr>
              <td>{{ p.label }}</td>
              <td><code>{{ p.pan_masked }}</code></td>
              <td>{{ p.dp_id || '—' }}</td>
              <td class="num">{{ p.application_count }}</td>
              <td><input type="checkbox" [checked]="p.is_active" (change)="toggle(p)" /></td>
              <td><button class="link danger" (click)="remove(p)">Remove</button></td>
            </tr>
          } @empty {
            <tr><td colspan="6" class="empty">No PANs yet.</td></tr>
          }
        </tbody>
      </table>
    </div>
  `,
})
export class PansPage {
  private api = inject(ApiService);

  pans = signal<Pan[]>([]);
  busy = signal(false);
  error = signal('');
  form = { label: '', pan: '', dp_id: '' };

  constructor() {
    this.load();
  }

  valid() {
    return !!this.form.label.trim() && PAN_RE.test(this.form.pan);
  }

  load() {
    this.api.pans().subscribe({ next: (p) => this.pans.set(p.results), error: (e) => this.error.set(errorText(e)) });
  }

  add() {
    this.busy.set(true);
    this.error.set('');
    this.api.createPan(this.form).subscribe({
      next: () => { this.form = { label: '', pan: '', dp_id: '' }; this.busy.set(false); this.load(); },
      error: (e) => { this.error.set(errorText(e)); this.busy.set(false); },
    });
  }

  toggle(p: Pan) {
    this.api.updatePan(p.id, { is_active: !p.is_active }).subscribe({
      next: () => this.load(),
      error: (e) => this.error.set(errorText(e)),
    });
  }

  remove(p: Pan) {
    const msg = p.application_count
      ? `${p.label} has application history, so it will be deactivated rather than deleted. Continue?`
      : `Delete ${p.label}?`;
    if (!confirm(msg)) return;
    this.api.deletePan(p.id).subscribe({ next: () => this.load(), error: (e) => this.error.set(errorText(e)) });
  }
}
