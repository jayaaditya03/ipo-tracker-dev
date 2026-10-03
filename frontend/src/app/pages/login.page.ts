import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { errorText } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { AuthShell } from './auth-shell';

@Component({
  imports: [FormsModule, AuthShell],
  template: `
    <app-auth-shell heading="Sign in" altText="Don't have an account?" altLink="/register">
      @if (error()) { <div class="alert alert-danger">{{ error() }}</div> }
      <form (ngSubmit)="submit()">
        <div class="form-group mb-3">
          <label class="form-label" for="email">Email address</label>
          <input id="email" type="email" name="email" class="form-control" [(ngModel)]="email" required autocomplete="email" />
        </div>
        <div class="form-group mb-3">
          <label class="form-label" for="password">Password</label>
          <input id="password" type="password" name="password" class="form-control" [(ngModel)]="password" required
            autocomplete="current-password" />
        </div>
        <div class="d-grid mt-4">
          <button class="btn btn-primary" type="submit" [disabled]="busy()">{{ busy() ? 'Signing in…' : 'Sign in' }}</button>
        </div>
      </form>
    </app-auth-shell>
  `,
})
export class LoginPage {
  private auth = inject(AuthService);
  private router = inject(Router);

  email = '';
  password = '';
  busy = signal(false);
  error = signal('');

  submit() {
    this.busy.set(true);
    this.error.set('');
    this.auth.login(this.email, this.password).subscribe({
      next: () => this.router.navigate(['/']),
      error: (e) => {
        this.error.set(e.status === 401 ? 'Wrong email or password.' : errorText(e));
        this.busy.set(false);
      },
    });
  }
}
