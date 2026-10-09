import { InrPipe, TonePipe } from './format';

describe('InrPipe', () => {
  const pipe = new InrPipe();

  it('formats DRF decimal strings with Indian grouping', () => {
    expect(pipe.transform('123456.00')).toBe('₹1,23,456');
  });

  it('keeps the sign on losses', () => {
    expect(pipe.transform('-750.00')).toContain('750');
    expect(pipe.transform('-750.00')).toMatch(/^-/);
  });

  it('shows a dash for missing values but formats zero', () => {
    expect(pipe.transform(null)).toBe('—');
    expect(pipe.transform(undefined)).toBe('—');
    expect(pipe.transform('')).toBe('—');
    expect(pipe.transform(0)).toBe('₹0');
  });
});

describe('TonePipe', () => {
  const pipe = new TonePipe();

  it('colours results', () => {
    expect(pipe.transform('ALLOTTED')).toBe('bg-light-success');
    expect(pipe.transform('REJECTED')).toBe('bg-light-danger');
    expect(pipe.transform('SOMETHING_NEW')).toBe('bg-light-secondary');
  });
});
