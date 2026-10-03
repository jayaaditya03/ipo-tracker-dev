import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService, errorText } from '../core/api.service';
import { Pan } from '../core/models';

const PAN_RE = /^[A-Z]{5}[0-9]{4}[A-Z]$/;

@Component({
  imports: [FormsModule],
  template: `
    <div class="mb-3">
      <h4 class="mb-1">PANs</h4>
      <p class="text-muted mb-0">Everyone you apply for. PANs are encrypted on the server and only ever shown masked.</p>
    </div>
    @if (error()) { <div class="alert alert-danger">{{ error() }}</div> }

    <div class="row">
      <div class="col-xl-4">
        <div class="card">
          <div class="card-header"><h5 class="mb-0">Add a PAN</h5></div>
          <div class="card-body">
            <form (ngSubmit)="add()">
              <div class="mb-3">
                <label class="form-label" for="label">Label</label>
                <input id="label" name="label" class="form-control" [(ngModel)]="form.label" placeholder="Self, Mother…" required />
              </div>
              <div class="mb-3">
                <label class="form-label" for="pan">PAN</label>
                <input id="pan" name="pan" class="form-control text-uppercase" [(ngModel)]="form.pan" maxlength="10"
                  placeholder="ABCDE1234F" (ngModelChange)="form.pan = $event.toUpperCase()" required
                  [class.is-invalid]="form.pan.length === 10 && !panOk()" />
                <div class="form-text">Five letters, four digits, one letter.</div>
              </div>
              <div class="mb-3">
                <label class="form-label" for="dp_id">Demat / DP ID <span class="text-muted">(optional)</span></label>
                <input id="dp_id" name="dp_id" class="form-control" [(ngModel)]="form.dp_id" />
              </div>
              <div class="d-grid">
                <button class="btn btn-primary" type="submit" [disabled]="busy() || !valid()">{{ busy() ? 'Adding…' : 'Add PAN' }}</button>
              </div>
            </form>
          </div>
        </div>
      </div>

      <div class="col-xl-8">
        <div class="card">
          <div class="card-header"><h5 class="mb-0">Your PANs</h5></div>
          <div class="table-responsive">
            <table class="table table-hover mb-0">
              <thead><tr><th>Label</th><th>PAN</th><th>DP ID</th><th class="num">Applications</th><th>Active</th><th></th></tr></thead>
              <tbody>
                @for (p of pans(); track p.id) {
                  <tr [class.text-muted]="!p.is_active">
                    <td class="f-w-600">{{ p.label }}</td>
                    <td><code>{{ p.pan_masked }}</code></td>
                    <td>{{ p.dp_id || '—' }}</td>
                    <td class="num">{{ p.application_count }}</td>
                    <td>
                      <div class="form-check form-switch mb-0">
                        <input class="form-check-input" type="checkbox" role="switch" [checked]="p.is_active" (change)="toggle(p)"
                          [attr.aria-label]="'Active: ' + p.label" />
                      </div>
                    </td>
                    <td class="text-end"><button class="btn btn-sm btn-outline-danger" (click)="remove(p)">Remove</button></td>
                  </tr>
                } @empty {
                  <tr><td colspan="6" class="text-center text-muted py-4">No PANs yet. Add yours first.</td></tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      </div>
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

  panOk() {
    return PAN_RE.test(this.form.pan);
  }

  valid() {
    return !!this.form.label.trim() && this.panOk();
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
