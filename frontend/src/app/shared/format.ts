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

/** Maps an application status to a Mantis badge colour class. */
@Pipe({ name: 'tone' })
export class TonePipe implements PipeTransform {
  transform(status: string): string {
    switch (status) {
      case 'OPEN': case 'APPLIED': return 'bg-light-primary';
      case 'ALLOTTED': case 'PARTIAL': return 'bg-light-success';
      case 'REJECTED': case 'WITHDRAWN': return 'bg-light-danger';
      case 'DRAFT': return 'bg-light-secondary';
      default: return 'bg-light-secondary';
    }
  }
}
