export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={className}>
      <defs>
        <linearGradient id="af-logo" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2a78d6" />
          <stop offset="1" stopColor="#0d366b" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#af-logo)" />
      <path d="M8 23 L14.5 9 L21 23" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M11 18.5 H18" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="23.5" cy="10.5" r="2.4" fill="#86b6ef" />
    </svg>
  );
}
