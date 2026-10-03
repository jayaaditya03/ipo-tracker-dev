import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';

import { environment } from '../../environments/environment';
import { LoginResponse, User } from './models';

const ACCESS = 'ipo.access';
const REFRESH = 'ipo.refresh';
const USER = 'ipo.user';

/**
 * Holds the JWT pair and the signed-in user.
 *
 * Tokens live in localStorage so a reload keeps you signed in. That is the
 * usual trade-off for a SPA talking to a separate API; the 30-minute access
 * lifetime set in Django limits what a leaked token is worth.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);
  private base = `${environment.apiUrl}/auth`;

  readonly user = signal<User | null>(readJson<User>(USER));
  readonly isLoggedIn = computed(() => this.user() !== null && !!this.accessToken);

  get accessToken(): string | null {
    return localStorage.getItem(ACCESS);
  }
  get refreshToken(): string | null {
    return localStorage.getItem(REFRESH);
  }

  login(email: string, password: string): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(`${this.base}/login/`, { email, password }).pipe(
      tap((res) => {
        localStorage.setItem(ACCESS, res.access);
        localStorage.setItem(REFRESH, res.refresh);
        this.setUser(res.user);
      }),
    );
  }

  register(body: { email: string; full_name: string; password: string; password_confirm: string }) {
    return this.http.post<User>(`${this.base}/register/`, body);
  }

  /** Swap the refresh token for a new pair. ROTATE_REFRESH_TOKENS is on, so both change. */
  refresh(): Observable<{ access: string; refresh?: string }> {
    return this.http
      .post<{ access: string; refresh?: string }>(`${this.base}/refresh/`, { refresh: this.refreshToken })
      .pipe(
        tap((res) => {
          localStorage.setItem(ACCESS, res.access);
          if (res.refresh) localStorage.setItem(REFRESH, res.refresh);
        }),
      );
  }

  loadMe(): Observable<User> {
    return this.http.get<User>(`${this.base}/me/`).pipe(tap((u) => this.setUser(u)));
  }

  logout(): void {
    localStorage.removeItem(ACCESS);
    localStorage.removeItem(REFRESH);
    localStorage.removeItem(USER);
    this.user.set(null);
    this.router.navigate(['/login']);
  }

  private setUser(u: User): void {
    localStorage.setItem(USER, JSON.stringify(u));
    this.user.set(u);
  }
}

function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}
