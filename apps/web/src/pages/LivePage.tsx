import { useEffect, useMemo, useState } from "react";
import { api, Detection, Overview, WS_URL } from "../api";

const CLASS_LABEL: Record<string, string> = {
  car: "Ô tô",
  motorcycle: "Xe máy",
  other: "Khác",
  unknown: "Chưa rõ",
};

export default function LivePage() {
  const [items, setItems] = useState<Detection[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [vehicleClass, setVehicleClass] = useState("");
  const [brand, setBrand] = useState("");
  const [color, setColor] = useState("");

  const query = useMemo(() => {
    const q = new URLSearchParams({ limit: "40" });
    if (vehicleClass) q.set("vehicle_class", vehicleClass);
    if (brand.trim()) q.set("vehicle_brand", brand.trim());
    if (color.trim()) q.set("vehicle_color", color.trim());
    return `?${q}`;
  }, [vehicleClass, brand, color]);

  const load = () =>
    api
      .detections(query)
      .then(setItems)
      .catch((e) => setError(String(e)));

  useEffect(() => {
    load();
    api.overview().then(setOverview).catch(() => null);

    const ws = new WebSocket(WS_URL);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "detection" && msg.detection) {
          const d = msg.detection as Detection;
          const okClass = !vehicleClass || d.vehicle_class === vehicleClass;
          const okBrand =
            !brand.trim() ||
            (d.vehicle_brand || "").toLowerCase().includes(brand.trim().toLowerCase());
          const okColor =
            !color.trim() ||
            (d.vehicle_color || "").toLowerCase() === color.trim().toLowerCase();
          if (okClass && okBrand && okColor) {
            setItems((prev) => [d, ...prev].slice(0, 80));
          }
          api.overview().then(setOverview).catch(() => null);
        }
      } catch {
        /* ignore */
      }
    };
    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 20000);
    return () => {
      clearInterval(ping);
      ws.close();
    };
  }, [query, vehicleClass, brand, color]);

  return (
    <div className="space-y-4 md:space-y-6">
      <header className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl md:text-2xl font-semibold">Trực tiếp</h2>
          <p className="text-slate-400 text-sm mt-1">
            Nhận diện thời gian thực · lọc loại xe / màu / hãng
          </p>
        </div>
        <div
          className={`text-xs px-2.5 py-1 rounded-lg border ${
            connected ? "border-ok/40 text-ok" : "border-danger/40 text-danger"
          }`}
        >
          {connected ? "Đã kết nối" : "Mất kết nối"}
        </div>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
        <label className="text-sm space-y-1 block">
          <span className="text-slate-500 text-xs">Loại xe</span>
          <select
            className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
            value={vehicleClass}
            onChange={(e) => setVehicleClass(e.target.value)}
          >
            <option value="">Tất cả</option>
            <option value="car">Ô tô</option>
            <option value="motorcycle">Xe máy</option>
            <option value="other">Khác</option>
            <option value="unknown">Chưa rõ</option>
          </select>
        </label>
        <label className="text-sm space-y-1 block">
          <span className="text-slate-500 text-xs">Màu xe</span>
          <input
            className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
            value={color}
            onChange={(e) => setColor(e.target.value)}
            placeholder="Trắng / Xanh…"
          />
        </label>
        <label className="text-sm space-y-1 block">
          <span className="text-slate-500 text-xs">Hãng xe</span>
          <input
            className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
            value={brand}
            onChange={(e) => setBrand(e.target.value)}
            placeholder="Toyota / Honda…"
          />
        </label>
        <div className="flex items-end">
          <button
            type="button"
            className="w-full text-sm border border-line rounded-lg px-3 py-2.5 hover:bg-white/5"
            onClick={() => load()}
          >
            Áp dụng lọc
          </button>
        </div>
      </div>

      {overview && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 md:gap-3">
          {[
            ["Nhận diện 24h", overview.detections_24h],
            ["Vi phạm 24h", overview.violations_24h],
            ["Xe trong khu vực", overview.vehicles_inside],
            ["Camera đang bật", overview.cameras_enabled],
            ["Camera kết nối", overview.cameras_connected],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-xl border border-line bg-panel px-3 py-3">
              <div className="text-xs text-slate-500 leading-snug">{label}</div>
              <div className="text-xl md:text-2xl font-semibold mt-1 font-mono">{value}</div>
            </div>
          ))}
        </div>
      )}

      {error && <div className="text-danger text-sm">{error}</div>}

      <div className="grid gap-2 md:gap-3">
        {items.map((d) => (
          <article
            key={d.id}
            className="flex gap-3 md:gap-4 rounded-xl border border-line bg-panel/70 p-3 items-start md:items-center"
          >
            <Thumb detection={d} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-base md:text-lg tracking-wide">
                  {d.plate_number || "—"}
                </span>
                {d.vehicle_class && (
                  <Badge
                    color={d.vehicle_class === "motorcycle" ? "warn" : "accent"}
                    text={CLASS_LABEL[d.vehicle_class] || d.vehicle_class}
                  />
                )}
                {d.vehicle_color && <Badge color="ok" text={String(d.vehicle_color)} />}
                {d.passage_direction && (
                  <Badge
                    color={d.passage_direction === "entry" ? "ok" : "accent"}
                    text={d.passage_direction === "entry" ? "VÀO" : "RA"}
                  />
                )}
                {d.seatbelt_main === "WithoutSafeBelt" && (
                  <Badge color="danger" text="Không dây an toàn" />
                )}
                {d.calling && <Badge color="warn" text="Gọi điện" />}
                {d.smoking && <Badge color="warn" text="Hút thuốc" />}
                {(d.unlicensed || Boolean(d.meta?.unlicensed)) && (
                  <Badge color="danger" text="Không biển" />
                )}
                {d.watched && <Badge color="danger" text="Truy vết" />}
                {(d.speed_status === "overspeed" ||
                  (d.speed != null &&
                    d.limit_max != null &&
                    d.speed > d.limit_max)) && (
                  <Badge
                    color="danger"
                    text={`Vượt tốc ${d.speed} km/h${d.limit_max != null ? `/${d.limit_max}` : ""}`}
                  />
                )}
                {d.speed_status === "underspeed" && (
                  <Badge color="warn" text={`Dưới tốc ${d.speed} km/h`} />
                )}
              </div>
              <div className="text-sm text-slate-400 mt-1 break-words">
                {[
                  d.vehicle_brand,
                  d.vehicle_model,
                  d.vehicle_category,
                  d.vehicle_color,
                  d.speed != null ? `${d.speed} km/h` : null,
                ]
                  .filter(Boolean)
                  .join(" · ") || d.event_code}
              </div>
              <div className="text-xs text-slate-500 mt-1 font-mono">
                {d.event_utc ? new Date(d.event_utc).toLocaleString("vi-VN") : "—"}
              </div>
            </div>
          </article>
        ))}
        {!items.length && !error && (
          <div className="text-slate-500 text-sm border border-dashed border-line rounded-xl p-6 text-center">
            Chưa có sự kiện. Thêm camera và chạy bộ thu sự kiện.
          </div>
        )}
      </div>
    </div>
  );
}

function Thumb({ detection }: { detection: Detection }) {
  const kind =
    detection.image_paths?.plate
      ? "plate"
      : detection.image_paths?.vehicle
        ? "vehicle"
        : detection.image_paths
          ? Object.keys(detection.image_paths)[0]
          : null;
  if (!kind) {
    return <div className="w-20 h-14 md:w-28 md:h-20 rounded-lg bg-ink border border-line shrink-0" />;
  }
  return (
    <img
      src={api.mediaUrl(detection.id, kind)}
      alt=""
      className="w-20 h-14 md:w-28 md:h-20 object-cover rounded-lg border border-line shrink-0 bg-ink"
    />
  );
}

function Badge({ text, color }: { text: string; color: "ok" | "accent" | "warn" | "danger" }) {
  const map = {
    ok: "border-ok/40 text-ok bg-ok/10",
    accent: "border-accent/40 text-accent bg-accent/10",
    warn: "border-warn/40 text-warn bg-warn/10",
    danger: "border-danger/40 text-danger bg-danger/10",
  };
  return (
    <span className={`text-[10px] md:text-[11px] uppercase tracking-wide px-2 py-0.5 rounded border ${map[color]}`}>
      {text}
    </span>
  );
}
