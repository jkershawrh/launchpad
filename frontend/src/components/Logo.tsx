interface LogoProps {
  className?: string;
  height?: number;
}

export function RedHatLogo({ className = '', height = 40 }: LogoProps) {
  return (
    <img
      src="/logos/redhat.png"
      alt="Red Hat"
      height={height}
      style={{ height: `${height}px`, width: 'auto' }}
      className={className}
    />
  );
}

export function IntelLogo({ className = '', height = 32 }: LogoProps) {
  return (
    <img
      src="/logos/intel.png"
      alt="Intel"
      height={height}
      style={{ height: `${height}px`, width: 'auto' }}
      className={className}
    />
  );
}
