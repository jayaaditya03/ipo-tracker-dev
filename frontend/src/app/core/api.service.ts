import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import {
  Application, AppStatus, BulkApplyResult, Category, CheckResponse, DashboardSummary,
  Ipo, Page, Pan, StatusEvent,
} from './models';

type Query = Record<string, string | number | boolean | undefined | null>;

/** Drops empty values so `?status=` never reaches django-filter. */
function params(q: Query = {}): HttpParams {
  let p = new HttpParams();
  for (const [k, v] of Object.entries(q)) {
    if (v !== undefined && v !== null && v !== '') p = p.set(k, String(v));
  }
  return p;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private base = environment.apiUrl;

  // ---------------------------------------------------------------- IPOs
  ipos(q?: Query): Observable<Page<Ipo>> {
    return this.http.get<Page<Ipo>>(`${this.base}/ipos/`, { params: params(q) });
  }
  ipo(id: number): Observable<Ipo> {
    return this.http.get<Ipo>(`${this.base}/ipos/${id}/`);
  }
  openNow(): Observable<Ipo[]> {
    return this.http.get<Ipo[]>(`${this.base}/ipos/open_now/`);
  }

  // ---------------------------------------------------------------- PANs
  pans(q?: Query): Observable<Page<Pan>> {
    return this.http.get<Page<Pan>>(`${this.base}/pans/`, { params: params({ page_size: 100, ...q }) });
  }
  createPan(body: { label: string; pan: string; dp_id?: string }): Observable<Pan> {
    return this.http.post<Pan>(`${this.base}/pans/`, body);
  }
  updatePan(id: number, body: Partial<{ label: string; dp_id: string; is_active: boolean }>): Observable<Pan> {
    return this.http.patch<Pan>(`${this.base}/pans/${id}/`, body);
  }
  deletePan(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/pans/${id}/`);
  }

  // -------------------------------------------------------- applications
  applications(q?: Query): Observable<Page<Application>> {
    return this.http.get<Page<Application>>(`${this.base}/applications/`, { params: params(q) });
  }
  bulkApply(body: {
    ipo_id: number; pan_ids: number[]; category: Category; lots: number; mark_applied: boolean;
  }): Observable<BulkApplyResult> {
    return this.http.post<BulkApplyResult>(`${this.base}/applications/bulk/`, body);
  }
  setStatus(id: number, body: { status: AppStatus; shares_allotted?: number; note?: string }): Observable<Application> {
    return this.http.post<Application>(`${this.base}/applications/${id}/set_status/`, body);
  }
  updateApplication(id: number, body: Partial<Pick<Application, 'application_number' | 'bank_reference' | 'notes' | 'lots'>>): Observable<Application> {
    return this.http.patch<Application>(`${this.base}/applications/${id}/`, body);
  }
  deleteApplication(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/applications/${id}/`);
  }
  /** Ask the registrars. No body = every pending application whose allotment date has arrived. */
  checkAllotments(body: { ipo_id?: number; application_ids?: number[] } = {}): Observable<CheckResponse> {
    return this.http.post<CheckResponse>(`${this.base}/applications/check/`, body);
  }
  events(id: number): Observable<StatusEvent[]> {
    return this.http.get<StatusEvent[]>(`${this.base}/applications/${id}/events/`);
  }

  // ------------------------------------------------------------ dashboard
  summary(): Observable<DashboardSummary> {
    return this.http.get<DashboardSummary>(`${this.base}/dashboard/summary/`);
  }
}

/** Flattens a DRF error body into one readable line. */
export function errorText(err: unknown): string {
  const body = (err as { error?: unknown })?.error;
  if (!body) return 'Something went wrong. Is the API running?';
  if (typeof body === 'string') return body;
  const parts: string[] = [];
  for (const [field, val] of Object.entries(body as Record<string, unknown>)) {
    const msg = Array.isArray(val) ? val.join(' ') : String(val);
    parts.push(field === 'detail' || field === 'non_field_errors' ? msg : `${field}: ${msg}`);
  }
  return parts.join(' · ');
}
