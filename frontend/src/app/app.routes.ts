import { Routes } from '@angular/router';

import { authGuard, guestGuard } from './core/auth.guard';
import { AdminLayout } from './theme/layouts/admin-layout/admin-layout.component';
import { GuestLayoutComponent } from './theme/layouts/guest-layout/guest-layout.component';

// Signed-in pages render inside the Mantis sidebar layout; login and
// register use the bare guest layout. Every page is lazy-loaded.
export const routes: Routes = [
  {
    path: '',
    component: AdminLayout,
    canActivate: [authGuard],
    children: [
      { path: '', title: 'Dashboard · IPO-PRO',
        loadComponent: () => import('./pages/dashboard.page').then((m) => m.DashboardPage) },
      { path: 'ipos', title: 'IPOs · IPO-PRO',
        loadComponent: () => import('./pages/ipo-list.page').then((m) => m.IpoListPage) },
      { path: 'ipos/:id', title: 'IPO · IPO-PRO',
        loadComponent: () => import('./pages/ipo-detail.page').then((m) => m.IpoDetailPage) },
      { path: 'applications', title: 'Applications · IPO-PRO',
        loadComponent: () => import('./pages/applications.page').then((m) => m.ApplicationsPage) },
      { path: 'pans', title: 'PANs · IPO-PRO',
        loadComponent: () => import('./pages/pans.page').then((m) => m.PansPage) }
    ]
  },
  {
    path: '',
    component: GuestLayoutComponent,
    canActivate: [guestGuard],
    children: [
      { path: 'login', title: 'Sign in · IPO-PRO',
        loadComponent: () => import('./pages/login.page').then((m) => m.LoginPage) },
      { path: 'register', title: 'Create account · IPO-PRO',
        loadComponent: () => import('./pages/register.page').then((m) => m.RegisterPage) }
    ]
  },
  { path: '**', redirectTo: '' }
];
