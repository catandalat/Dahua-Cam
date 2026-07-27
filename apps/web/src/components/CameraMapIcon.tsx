/** Custom SVG map markers for cameras — colored by listener status. */

export const ICON_OPTIONS = [
  { id: "camera", label: "Camera" },
  { id: "dome", label: "Dome" },
  { id: "ptz", label: "PTZ" },
  { id: "radar", label: "Radar ANPR" },
  { id: "gate", label: "Cổng" },
] as const;

export function statusColor(status?: string): string {
  switch (status) {
    case "connected":
      return "#22c55e";
    case "connecting":
      return "#3d9cf0";
    case "error":
      return "#ef4444";
    case "disconnected":
      return "#94a3b8";
    default:
      return "#64748b";
  }
}

export function CameraMapIcon({
  icon = "camera",
  status = "unknown",
  size = 40,
  pulse = false,
}: {
  icon?: string;
  status?: string;
  size?: number;
  pulse?: boolean;
}) {
  const fill = statusColor(status);
  const w = size;
  const h = size * 1.15;

  return (
    <div className="relative" style={{ width: w, height: h }}>
      {pulse && (
        <span
          className="absolute inset-0 rounded-full animate-ping opacity-30"
          style={{ background: fill, top: "8%", height: "70%" }}
        />
      )}
      <svg
        width={w}
        height={h}
        viewBox="0 0 48 56"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="relative drop-shadow-md"
        aria-hidden
      >
        {/* teardrop pin */}
        <path
          d="M24 54C24 54 44 36.5 44 22C44 10.954 35.046 2 24 2C12.954 2 4 10.954 4 22C4 36.5 24 54 24 54Z"
          fill={fill}
          stroke="#0f172a"
          strokeWidth="1.5"
          strokeOpacity="0.35"
        />
        <circle cx="24" cy="22" r="13" fill="#0f172a" fillOpacity="0.22" />
        <circle cx="24" cy="22" r="11.5" fill="#ffffff" />
        <g transform="translate(24 22)">{glyph(icon)}</g>
      </svg>
    </div>
  );
}

function glyph(icon: string) {
  const stroke = "#0f172a";
  switch (icon) {
    case "dome":
      return (
        <g fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round">
          <path d="M-7 3.5h14" />
          <path d="M-6 3.5C-6 -2 -3.5 -7 0 -7s6 5 6 10.5" fill="#e2e8f0" />
          <circle cx="0" cy="-1" r="2.2" fill={stroke} />
        </g>
      );
    case "ptz":
      return (
        <g fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round">
          <rect x="-6.5" y="-4" width="13" height="9" rx="2" fill="#e2e8f0" />
          <circle cx="0" cy="0.5" r="3" fill="#94a3b8" stroke={stroke} />
          <circle cx="0" cy="0.5" r="1.2" fill={stroke} />
          <path d="M0 -7v2M-4 -6l2 2M4 -6l-2 2" />
        </g>
      );
    case "radar":
      return (
        <g fill="none" stroke={stroke} strokeWidth="1.5" strokeLinecap="round">
          <path d="M0 5V-2" />
          <path d="M-5 5h10" />
          <path d="M-6 -1a6 6 0 0 1 12 0" />
          <path d="M-3.5 0.5a3.5 3.5 0 0 1 7 0" />
          <circle cx="0" cy="-1" r="1.3" fill={stroke} />
        </g>
      );
    case "gate":
      return (
        <g fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round">
          <path d="M-7 5V-5h4v10M3 5V-5h4v10" fill="#e2e8f0" />
          <path d="M-3 -2h6M-3 1h6" />
        </g>
      );
    case "camera":
    default:
      return (
        <g fill="none" stroke={stroke} strokeWidth="1.6" strokeLinejoin="round">
          <rect x="-7" y="-4.5" width="11" height="9" rx="1.8" fill="#e2e8f0" />
          <path d="M4 -2.2l4-2.3v8.5l-4-2.3z" fill="#cbd5e1" />
          <circle cx="-1.5" cy="0" r="2.4" fill="#94a3b8" stroke={stroke} />
          <circle cx="-1.5" cy="0" r="1" fill={stroke} />
        </g>
      );
  }
}
