/**
 * There is no icon package in this app and nothing else can be installed, so every glyph
 * on the site is drawn here. All of them share a 24-unit box and a 1.5 stroke so they sit
 * on the same optical weight when mixed in a row.
 */

type IconProps = { className?: string };

function Frame({ className, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {children}
    </svg>
  );
}

export function IconFlow({ className }: IconProps) {
  return (
    <Frame className={className}>
      <rect x="2.5" y="3.5" width="7" height="5" rx="1.5" />
      <rect x="14.5" y="15.5" width="7" height="5" rx="1.5" />
      <path d="M6 8.5v5.5a4 4 0 0 0 4 4h4.5" />
      <path d="M12.5 15.5 15 18l-2.5 2.5" />
    </Frame>
  );
}

export function IconRollup({ className }: IconProps) {
  return (
    <Frame className={className}>
      <path d="M3 20.5h18" />
      <rect x="4.5" y="12" width="3.5" height="6" rx="1" />
      <rect x="10.25" y="8" width="3.5" height="10" rx="1" />
      <rect x="16" y="4" width="3.5" height="14" rx="1" />
    </Frame>
  );
}

export function IconClock({ className }: IconProps) {
  return (
    <Frame className={className}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </Frame>
  );
}

export function IconKey({ className }: IconProps) {
  return (
    <Frame className={className}>
      <circle cx="7.5" cy="12" r="3.75" />
      <path d="M11.25 12H21" />
      <path d="M17.5 12v3.25" />
      <path d="M20.5 12v2.25" />
    </Frame>
  );
}

export function IconShield({ className }: IconProps) {
  return (
    <Frame className={className}>
      <path d="M12 3 19 5.75v5.4c0 4-2.85 7.6-7 9.35-4.15-1.75-7-5.35-7-9.35v-5.4L12 3Z" />
      <path d="m9 12 2.15 2.15L15.25 10" />
    </Frame>
  );
}

export function IconLayers({ className }: IconProps) {
  return (
    <Frame className={className}>
      <path d="m12 3 8.5 4.25L12 11.5 3.5 7.25 12 3Z" />
      <path d="m3.5 12 8.5 4.25L20.5 12" />
      <path d="m3.5 16.5 8.5 4.25 8.5-4.25" />
    </Frame>
  );
}

export function IconCheck({ className }: IconProps) {
  return (
    <Frame className={className}>
      <path d="m4.5 12.5 4.5 4.5 10.5-11" />
    </Frame>
  );
}

export function IconArrow({ className }: IconProps) {
  return (
    <Frame className={className}>
      <path d="M4.5 12h15" />
      <path d="m13.5 6 6 6-6 6" />
    </Frame>
  );
}

export function IconQuote({ className }: IconProps) {
  return (
    <svg viewBox="0 0 32 24" fill="currentColor" aria-hidden="true" className={className}>
      <path d="M0 24V13.2C0 5.9 4.2 1.4 12.1 0l1.2 3.9C8.6 5.3 6.2 7.7 6 11h6v13H0Zm18.7 0V13.2C18.7 5.9 22.9 1.4 30.8 0L32 3.9c-4.7 1.4-7.1 3.8-7.3 7.1h6v13h-12Z" />
    </svg>
  );
}
