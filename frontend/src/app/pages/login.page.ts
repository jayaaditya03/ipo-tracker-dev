import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { errorText } from '../core/api.service';
import { AuthService } from '../core/auth.service';

@Component({
  imports: [FormsModule, RouterLink],
  template: `
    <div class="card">
      <h1>Sign in</h1>
      @if (error()) { <div class="error">{{ error() }}</div> }
      <form (ngSubmit)="submit()">
        <label>Email <input type="email" name="email" [(ngModel)]="email" required autocomplete="email" /></label>
        <label>Password <input type="password" name="password" [(ngModel)]="password" required autocomplete="current-password" /></label>
        <button class="primary" type="submit" [disabled]="busy()">{{ busy() ? 'Signing in…' : 'Sign in' }}</button>
      </form>
      <p class="muted">No account? <a routerLink="/register">Create one</a></p>
    </div>
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
