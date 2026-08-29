/**
 * Customer wordmarks. Every company here is invented for the demo, so there is no image to
 * license and none to load — each mark is a few paths plus a <text> node that inherits the
 * page's own sans face. Kestrel and Halden are the two names the demo agent's battlecards
 * cite by name; the rest are filler so the row does not look like a two-customer company.
 */

type MarkProps = { className?: string };

const wordProps = {
  x: 34,
  y: 19,
  fontSize: 13,
  fontWeight: 600,
  letterSpacing: 1.6,
  fill: "currentColor",
} as const;

function Mark({
  title,
  children,
  className,
  width = 178,
}: MarkProps & { title: string; children: React.ReactNode; width?: number }) {
  return (
    <svg
      viewBox={`0 0 ${width} 28`}
      role="img"
      aria-label={title}
      className={className}
      style={{ width: `${width / 28}em` }}
    >
      {children}
    </svg>
  );
}

export function KestrelLogistics({ className }: MarkProps) {
  return (
    <Mark title="Kestrel Logistics" className={className} width={196}>
      <path d="M4 22 14 4l4.5 8-4 3.6L22 22H4Z" fill="currentColor" />
      <text {...wordProps}>KESTREL</text>
      <text {...wordProps} x={122} fontWeight={400} opacity={0.6}>
        LOG.
      </text>
    </Mark>
  );
}

export function HaldenGroup({ className }: MarkProps) {
  return (
    <Mark title="Halden Group" className={className} width={190}>
      <rect x="4" y="5" width="18" height="18" rx="3" fill="currentColor" opacity={0.25} />
      <rect x="9.5" y="10.5" width="12" height="12" rx="2" fill="currentColor" />
      <text {...wordProps}>HALDEN</text>
      <text {...wordProps} x={122} fontWeight={400} opacity={0.6}>
        GRP.
      </text>
    </Mark>
  );
}

export function MeridianHealth({ className }: MarkProps) {
  return (
    <Mark title="Meridian Health" className={className} width={172}>
      <circle cx="13" cy="14" r="9.5" fill="none" stroke="currentColor" strokeWidth={2.4} />
      <path d="M3.5 14h19" stroke="currentColor" strokeWidth={2.4} />
      <text {...wordProps}>MERIDIAN</text>
    </Mark>
  );
}

export function SouthportRail({ className }: MarkProps) {
  return (
    <Mark title="Southport Rail" className={className} width={174}>
      <path d="M5 8h18M5 14h18M5 20h11" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round" />
      <text {...wordProps}>SOUTHPORT</text>
    </Mark>
  );
}

export function ArdenneFoods({ className }: MarkProps) {
  return (
    <Mark title="Ardenne Foods" className={className} width={166}>
      <path
        d="M22 5c0 9.4-4.6 15.5-11 17.8C10.2 14 14.4 7.4 22 5Z"
        fill="currentColor"
      />
      <path d="M6 23c1.4-5 4.2-9.2 8-12" stroke="currentColor" strokeWidth={2} fill="none" strokeLinecap="round" />
      <text {...wordProps}>ARDENNE</text>
    </Mark>
  );
}

export const CUSTOMER_MARKS = [
  KestrelLogistics,
  HaldenGroup,
  MeridianHealth,
  SouthportRail,
  ArdenneFoods,
];
