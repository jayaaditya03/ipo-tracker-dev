import { Routes } from '@angular/router';

import { authGuard, guestGuard } from './core/auth.guard';

// Every page is lazy-loaded, so the login screen does not ship the
// dashboard's code.
export const routes: Routes = [
  { path: 'login', canActivate: [guestGuard], title: 'Sign in',
    loadComponent: () => import('./pages/login.page').then((m) => m.LoginPage) },
  { path: 'register', canActivate: [guestGuard], title: 'Create account',
    loadComponent: () => import('./pages/register.page').then((m) => m.RegisterPage) },
  {
    path: '',
    canActivate: [authGuard],
    children: [
      { path: '', title: 'Dashboard',
        loadComponent: () => import('./pages/dashboard.page').then((m) => m.DashboardPage) },
      { path: 'ipos', title: 'IPOs',
        loadComponent: () => import('./pages/ipo-list.page').then((m) => m.IpoListPage) },
      { path: 'ipos/:id', title: 'IPO',
        loadComponent: () => import('./pages/ipo-detail.page').then((m) => m.IpoDetailPage) },
      { path: 'applications', title: 'Applications',
        loadComponent: () => import('./pages/applications.page').then((m) => m.ApplicationsPage) },
      { path: 'pans', title: 'PANs',
        loadComponent: () => import('./pages/pans.page').then((m) => m.PansPage) },
    ],
  },
  { path: '**', redirectTo: '' },
];
