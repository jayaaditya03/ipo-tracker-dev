import { HttpErrorResponse, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { Observable, catchError, shareReplay, switchMap, throwError, finalize } from 'rxjs';

import { AuthService } from './auth.service';

// One in-flight refresh shared by every request that hits a 401 at once,
// so five parallel calls don't trigger five refreshes (and with token
// rotation, four of them would fail).
let refreshing$: Observable<unknown> | null = null;

const withToken = (req: HttpRequest<unknown>, token: string | null) =>
  token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);

  // Auth endpoints never carry a token and never trigger a refresh.
  if (req.url.includes('/auth/login/') || req.url.includes('/auth/register/') || req.url.includes('/auth/refresh/')) {
    return next(req);
  }

  return next(withToken(req, auth.accessToken)).pipe(
    catchError((err: HttpErrorResponse) => {
      if (err.status !== 401 || !auth.refreshToken) return throwError(() => err);

      refreshing$ ??= auth.refresh().pipe(
        shareReplay(1),
        finalize(() => (refreshing$ = null)),
      );

      return refreshing$.pipe(
        switchMap(() => next(withToken(req, auth.accessToken))),
        catchError((refreshErr) => {
          auth.logout();
          return throwError(() => refreshErr);
        }),
      );
    }),
  );
};
