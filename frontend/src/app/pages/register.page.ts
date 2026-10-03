import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { switchMap } from 'rxjs';

import { errorText } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { AuthShell } from './auth-shell';

@Component({
  imports: [FormsModule, AuthShell],
  template: `
    <app-auth-shell heading="Create account" altText="Already have an account?" altLink="/login">
      @if (error()) { <div class="alert alert-danger">{{ error() }}</div> }
      <form (ngSubmit)="submit()">
        <div class="form-group mb-3">
          <label class="form-label" for="full_name">Full name</label>
          <input id="full_name" name="full_name" class="form-control" [(ngModel)]="form.full_name" autocomplete="name" />
        </div>
        <div class="form-group mb-3">
          <label class="form-label" for="email">Email address</label>
          <input id="email" type="email" name="email" class="form-control" [(ngModel)]="form.email" required autocomplete="email" />
        </div>
        <div class="row">
          <div class="col-sm-6 form-group mb-3">
            <label class="form-label" for="password">Password</label>
            <input id="password" type="password" name="password" class="form-control" [(ngModel)]="form.password"
              required minlength="8" autocomplete="new-password" />
          </div>
          <div class="col-sm-6 form-group mb-3">
            <label class="form-label" for="password_confirm">Confirm password</label>
            <input id="password_confirm" type="password" name="password_confirm" class="form-control"
              [(ngModel)]="form.password_confirm" required autocomplete="new-password" />
          </div>
        </div>
        <p class="text-muted text-sm mb-0">At least 8 characters, not entirely numbers.</p>
        <div class="d-grid mt-4">
          <button class="btn btn-primary" type="submit" [disabled]="busy()">{{ busy() ? 'Creating…' : 'Create account' }}</button>
        </div>
      </form>
    </app-auth-shell>
  `,
})
export class RegisterPage {
  private auth = inject(AuthService);
  private router = inject(Router);

  form = { full_name: '', email: '', password: '', password_confirm: '' };
  busy = signal(false);
  error = signal('');

  submit() {
    this.busy.set(true);
    this.error.set('');
    this.auth
      .register(this.form)
      .pipe(switchMap(() => this.auth.login(this.form.email, this.form.password)))
      .subscribe({
        next: () => this.router.navigate(['/pans']),
        error: (e) => {
          this.error.set(errorText(e));
          this.busy.set(false);
        },
      });
  }
}
