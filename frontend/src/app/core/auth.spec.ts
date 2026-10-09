import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { environment } from '../../environments/environment';
import { authInterceptor } from './auth.interceptor';
import { AuthService } from './auth.service';

const API = environment.apiUrl;

describe('auth interceptor and AuthService', () => {
  let http: HttpClient;
  let ctrl: HttpTestingController;
  let auth: AuthService;

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('ipo.access', 'old-access');
    localStorage.setItem('ipo.refresh', 'old-refresh');
    localStorage.setItem('ipo.user', JSON.stringify({ id: 1, email: 'a@b.c', full_name: 'A', created_at: '' }));
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    ctrl = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthService);
    vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
  });

  afterEach(() => ctrl.verify());

  it('sends the access token on API calls', () => {
    http.get(`${API}/pans/`).subscribe();
    expect(ctrl.expectOne(`${API}/pans/`).request.headers.get('Authorization')).toBe('Bearer old-access');
  });

  it('never sends a token to the auth endpoints', () => {
    http.post(`${API}/auth/login/`, {}).subscribe();
    expect(ctrl.expectOne(`${API}/auth/login/`).request.headers.has('Authorization')).toBe(false);
  });

  it('refreshes once for concurrent 401s, then retries each with the new token', () => {
    const results: string[] = [];
    http.get<string>(`${API}/pans/`).subscribe((r) => results.push(r));
    http.get<string>(`${API}/ipos/`).subscribe((r) => results.push(r));

    ctrl.expectOne(`${API}/pans/`).flush(null, { status: 401, statusText: 'Unauthorized' });
    ctrl.expectOne(`${API}/ipos/`).flush(null, { status: 401, statusText: 'Unauthorized' });

    const refresh = ctrl.match(`${API}/auth/refresh/`);
    expect(refresh.length).toBe(1);
    expect(refresh[0].request.body).toEqual({ refresh: 'old-refresh' });
    refresh[0].flush({ access: 'new-access', refresh: 'new-refresh' });

    for (const url of [`${API}/pans/`, `${API}/ipos/`]) {
      const retry = ctrl.expectOne(url);
      expect(retry.request.headers.get('Authorization')).toBe('Bearer new-access');
      retry.flush('ok');
    }
    expect(results).toEqual(['ok', 'ok']);
    expect(localStorage.getItem('ipo.refresh')).toBe('new-refresh');
  });

  it('signs out when the refresh token is rejected', () => {
    let failed = false;
    http.get(`${API}/pans/`).subscribe({ error: () => (failed = true) });
    ctrl.expectOne(`${API}/pans/`).flush(null, { status: 401, statusText: 'Unauthorized' });
    ctrl.expectOne(`${API}/auth/refresh/`).flush(null, { status: 401, statusText: 'Unauthorized' });
    ctrl.expectOne(`${API}/auth/logout/`).flush({});

    expect(failed).toBe(true);
    expect(auth.isLoggedIn()).toBe(false);
    expect(localStorage.getItem('ipo.access')).toBeNull();
  });

  it('passes non-401 errors straight through', () => {
    let status = 0;
    http.get(`${API}/pans/`).subscribe({ error: (e) => (status = e.status) });
    ctrl.expectOne(`${API}/pans/`).flush(null, { status: 429, statusText: 'Too Many Requests' });
    expect(status).toBe(429);
  });

  it('logout revokes the refresh token on the server and clears local state', () => {
    auth.logout();
    const req = ctrl.expectOne(`${API}/auth/logout/`);
    expect(req.request.body).toEqual({ refresh: 'old-refresh' });
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush({});
    expect(auth.user()).toBeNull();
    expect(localStorage.getItem('ipo.refresh')).toBeNull();
  });

  it('logout still signs out locally when the server is unreachable', () => {
    auth.logout();
    ctrl.expectOne(`${API}/auth/logout/`).error(new ProgressEvent('error'));
    expect(auth.isLoggedIn()).toBe(false);
  });
});
