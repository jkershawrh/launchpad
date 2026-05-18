interface HwColorEntry {
  color: string;
  bg: string;
  done: string;
  labelColor: 'blue' | 'orange' | 'grey';
}

export const hwColors: Record<string, HwColorEntry> = {
  xeon6: {
    color: 'var(--rh-color--xeon6)',
    bg: 'var(--rh-color--xeon6-bg)',
    done: 'var(--rh-color--xeon6-done)',
    labelColor: 'blue',
  },
  gaudi: {
    color: 'var(--rh-color--gaudi)',
    bg: 'var(--rh-color--gaudi-bg)',
    done: 'var(--rh-color--gaudi-done)',
    labelColor: 'orange',
  },
  local: {
    color: 'var(--rh-color--local)',
    bg: 'var(--rh-color--local-bg)',
    done: 'var(--rh-color--local-done)',
    labelColor: 'grey',
  },
};

export type HwKey = keyof typeof hwColors;
