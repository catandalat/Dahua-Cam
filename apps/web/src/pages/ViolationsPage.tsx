import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, Violation } from "../api";
import { ZoomableImage } from "../components/ZoomableImage";

const TYPES: { value: string; label: string }[] = [
  { value: "", label: "Tất cả" },
  { value: "seatbelt", label: "Không dây an toàn" },
  { value: "calling", label: "Gọi điện" },
  { value: "smoking", label: "Hút thuốc" },
  { value: "unlicensed", label: "Không biển số" },
  { value: "retrograde", label: "Đi ngược chiều" },
  { value: "parking", label: "Đỗ sai quy định" },
  { value: "overline", label: "Lấn vạch" },
  { value: "pedestrian", label: "Người đi bộ" },
  { value: "jam", label: "Kẹt xe" },
  { value: "nonmotor_umbrella", label: "Xe máy che ô" },
  { value: "nonmotor_lane", label: "Xe máy sai làn" },
  { value: "nonmotor_overload", label: "Xe máy quá tải" },
  { value: "nonmotor_safehat", label: "Không mũ bảo hiểm" },
];

const TYPE_LABEL = Object.fromEntries(TYPES.filter((t) => t.value).map((t) => [t.value, t.label]));

export default function ViolationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [rows, setRows] = useState<Violation[]>([]);
  const [type, setType] = useState(searchParams.get("type") || "");

  const load = () => {
    const q = new URLSearchParams({ limit: "100" });
    if (type) q.set("type", type);
    api.violations(`?${q}`).then(setRows).catch(console.error);
  };

  useEffect(() => {
    load();
  }, [type]);

  return (
    <div className="space-y-4 md:space-y-6">
      <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <h2 className="text-xl md:text-2xl font-semibold">Vi phạm</h2>
          <p className="text-slate-400 text-sm mt-1">
            Dây an toàn, gọi điện và các sự kiện giao thông khác
          </p>
        </div>
        <select
          value={type}
          onChange={(e) => {
            const v = e.target.value;
            setType(v);
            if (v) setSearchParams({ type: v });
            else setSearchParams({});
          }}
          className="bg-ink border border-line rounded-lg px-3 py-2.5 text-sm w-full sm:w-auto"
        >
          {TYPES.map((t) => (
            <option key={t.value || "all"} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </header>

      <div className="grid gap-2 md:gap-3">
        {rows.map((v) => (
          <article
            key={v.id}
            className="flex gap-3 items-start md:items-center rounded-xl border border-line bg-panel/70 p-3"
          >
            {v.detection_id && v.image_paths ? (
              <ZoomableImage
                src={api.mediaUrl(
                  v.detection_id,
                  v.image_paths.plate
                    ? "plate"
                    : v.image_paths.vehicle
                      ? "vehicle"
                      : Object.keys(v.image_paths)[0],
                )}
                alt=""
                className="w-20 h-14 md:w-24 md:h-16 object-cover rounded-lg border border-line bg-ink shrink-0 block"
              />
            ) : (
              <div className="w-20 h-14 md:w-24 md:h-16 rounded-lg border border-line bg-ink shrink-0" />
            )}
            <div className="min-w-0">
              <div className="flex gap-2 items-center flex-wrap">
                <span className="font-mono text-base md:text-lg">{v.plate_number || "—"}</span>
                <span className="text-[10px] uppercase tracking-wide text-danger border border-danger/30 bg-danger/10 px-2 py-0.5 rounded">
                  {TYPE_LABEL[v.violation_type] || v.violation_type}
                </span>
              </div>
              <div className="text-xs text-slate-500 mt-1 font-mono">
                {v.event_utc ? new Date(v.event_utc).toLocaleString("vi-VN") : "—"}
              </div>
            </div>
          </article>
        ))}
        {!rows.length && (
          <div className="text-slate-500 text-sm border border-dashed border-line rounded-xl p-6 text-center">
            Chưa có vi phạm
          </div>
        )}
      </div>
    </div>
  );
}
