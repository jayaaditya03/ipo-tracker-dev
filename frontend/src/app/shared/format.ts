import { Pipe, PipeTransform } from '@angular/core';

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 });

/** "123456.00" → "₹1,23,456". Accepts the string decimals DRF sends. */
@Pipe({ name: 'inr' })
export class InrPipe implements PipeTransform {
  transform(v: string | number | null | undefined): string {
    if (v === null || v === undefined || v === '') return '—';
    return inr.format(Number(v));
  }
}

/** Maps a status code to a badge colour class. */
@Pipe({ name: 'tone' })
export class TonePipe implements PipeTransform {
  transform(status: string): string {
    switch (status) {
      case 'OPEN': case 'APPLIED': return 'info';
      case 'ALLOTTED': case 'PARTIAL': case 'LISTED': return 'good';
      case 'REJECTED': case 'WITHDRAWN': return 'bad';
      case 'UPCOMING': case 'DRAFT': return 'muted';
      default: return 'neutral';
    }
  }
}
