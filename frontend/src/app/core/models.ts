/**
 * Shapes returned by the Django API. Money arrives as strings because DRF
 * serialises DecimalField that way — convert with Number() only for display.
 */

export interface User {
  id: number;
  email: string;
  full_name: string;
  created_at: string;
  pan_count?: number;
}

export interface LoginResponse {
  access: string;
  refresh: string;
  user: User;
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Registrar {
  id: number;
  name: string;
  slug: string;
  status_check_url: string;
  website: string;
}

export type IpoStatus = 'UPCOMING' | 'OPEN' | 'CLOSED' | 'ALLOTTED' | 'LISTED' | 'WITHDRAWN';

/** What stage an issue is at. Distinct from an application's result. */
export const IPO_STATUS_LABELS: Record<IpoStatus, string> = {
  UPCOMING: 'Upcoming',
  OPEN: 'Open for bidding',
  CLOSED: 'Bidding closed',
  ALLOTTED: 'Allotment out',
  LISTED: 'Listed',
  WITHDRAWN: 'Withdrawn',
};

export const IPO_STATUS_TONES: Record<IpoStatus, string> = {
  UPCOMING: 'bg-light-warning',
  OPEN: 'bg-light-primary',
  CLOSED: 'bg-light-secondary',
  ALLOTTED: 'bg-light-secondary',
  LISTED: 'bg-light-secondary',
  WITHDRAWN: 'bg-light-danger',
};

export type Board = 'MAINBOARD' | 'SME';

export interface Ipo {
  id: number;
  name: string;
  symbol: string;
  board: Board;
  status: IpoStatus;
  registrar: Registrar;
  price_band_low: string | null;
  price_band_high: string | null;
  cutoff_price: string | null;
  lot_size: number | null;
  lot_amount: string | null;
  gmp: string | null;
  open_date: string | null;
  close_date: string | null;
  allotment_date: string | null;
  listing_date: string | null;
  dates_estimated: boolean;
  // detail only
  issue_size_cr?: string | null;
  refund_date?: string | null;
  listing_price?: string | null;
  listing_gain_pct?: string | null;
  my_application_count?: number;
}

export interface Pan {
  id: number;
  label: string;
  pan_masked: string;
  dp_id: string;
  is_active: boolean;
  application_count: number;
  created_at: string;
}

export type Category = 'RETAIL' | 'SHNI' | 'BHNI' | 'EMPLOYEE' | 'SHAREHOLDER';
export type AppStatus =
  | 'DRAFT' | 'APPLIED' | 'ALLOTTED' | 'PARTIAL' | 'REJECTED' | 'REFUNDED' | 'WITHDRAWN';

export const APP_STATUS_LABELS: Record<AppStatus, string> = {
  DRAFT: 'Not applied',
  APPLIED: 'Applied',
  ALLOTTED: 'Allotted',
  PARTIAL: 'Partially allotted',
  REJECTED: 'Not allotted',
  REFUNDED: 'Refunded',
  WITHDRAWN: 'Withdrawn',
};

export const CATEGORY_LABELS: Record<Category, string> = {
  RETAIL: 'Retail',
  SHNI: 'S-HNI (₹2–10L)',
  BHNI: 'B-HNI (above ₹10L)',
  EMPLOYEE: 'Employee',
  SHAREHOLDER: 'Shareholder',
};

export interface Application {
  id: number;
  ipo: Ipo;
  pan_id: number;
  pan_label: string;
  pan_masked: string;
  category: Category;
  status: AppStatus;
  status_display: string;
  lots: number;
  bid_price: string;
  shares_applied: number;
  amount_blocked: string;
  shares_allotted: number;
  listing_gain: string | null;
  application_number: string;
  bank_reference: string;
  notes: string;
  applied_at: string | null;
  checked_at: string | null;
  created_at: string;
}

export interface StatusEvent {
  id: number;
  from_status: string;
  to_status: string;
  source: string;
  note: string;
  created_at: string;
}

export interface BulkApplyResult {
  created: Application[];
  skipped: { pan_id: number; pan_label: string; reason: string }[];
  summary: { requested: number; created: number; skipped: number };
}

export interface DashboardSummary {
  applications: number;
  drafts: number;
  pending: number;
  allotted: number;
  rejected: number;
  blocked: string;
  invested: string;
  realised_gain: string;
  hit_rate: number;
  by_pan: { pan__id: number; pan__label: string; applications: number; allotted: number }[];
}

export type CheckOutcome = 'allotted' | 'not_allotted' | 'not_found' | 'not_published' | 'unsupported' | 'error';

export interface CheckRow {
  application_id: number;
  ipo_id: number;
  ipo_name: string;
  pan_label: string;
  pan_masked: string;
  registrar: string;
  status_check_url: string;
  outcome: CheckOutcome;
  status: AppStatus;
  shares_applied?: number | null;
  shares_allotted?: number | null;
  kept?: boolean;
  message: string;
}

export interface CheckResponse {
  results: CheckRow[];
  summary: Partial<Record<CheckOutcome, number>>;
}
