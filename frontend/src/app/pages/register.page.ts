import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { switchMap } from 'rxjs';

import { errorText } from '../core/api.service';
import { AuthService } from '../core/auth.service';

@Component({
  imports: [FormsModule, RouterLink],
  template: `
    <div class="card">
      <h1>Create account</h1>
      @if (error()) { <div class="error">{{ error() }}</div> }
      <form (ngSubmit)="submit()">
        <label>Full name <input name="full_name" [(ngModel)]="form.full_name" autocomplete="name" /></label>
        <label>Email <input type="email" name="email" [(ngModel)]="form.email" required autocomplete="email" /></label>
        <label>Password <input type="password" name="password" [(ngModel)]="form.password" required minlength="8" autocomplete="new-password" /></label>
        <label>Confirm password <input type="password" name="password_confirm" [(ngModel)]="form.password_confirm" required autocomplete="new-password" /></label>
        <button class="primary" type="submit" [disabled]="busy()">{{ busy() ? 'Creating…' : 'Create account' }}</button>
      </form>
      <p class="muted">Already registered? <a routerLink="/login">Sign in</a></p>
    </div>
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
