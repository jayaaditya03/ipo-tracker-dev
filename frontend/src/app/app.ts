import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from './core/auth.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    @if (auth.isLoggedIn()) {
      <header class="topbar">
        <a routerLink="/" class="brand">IPO Tracker</a>
        <nav>
          <a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }">Dashboard</a>
          <a routerLink="/ipos" routerLinkActive="active">IPOs</a>
          <a routerLink="/applications" routerLinkActive="active">Applications</a>
          <a routerLink="/pans" routerLinkActive="active">PANs</a>
        </nav>
        <div class="who">
          <span>{{ auth.user()?.full_name || auth.user()?.email }}</span>
          <button class="link" (click)="auth.logout()">Sign out</button>
        </div>
      </header>
    }
    <main [class.narrow]="!auth.isLoggedIn()">
      <router-outlet />
    </main>
  `,
})
export class App {
  protected auth = inject(AuthService);
}
