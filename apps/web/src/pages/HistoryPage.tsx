import { useEffect, useState } from "react";
import { api, Detection, Session } from "../api";
import { ZoomableImage } from "../components/ZoomableImage";

type Tab = "detections" | "sessions";

const CLASS_LABEL: Record<string, string> = {
  car: "Ô tô",
  motorcycle: "Xe máy",
  other: "Khác",
  unknown: "Chưa rõ",
};

export default function HistoryPage() {
  const [tab, setTab] = useState<Tab>("detections");
  const [dets, setDets] = useState<Detection[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [plate, setPlate] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    const dq = new URLSearchParams({ limit: "100" });
    const sq = new URLSearchParams({ limit: "100" });
    if (plate.trim()) {
      dq.set("plate", plate.trim());
      sq.set("plate", plate.trim());
    }
    Promise.all([api.detections(`?${dq}`), api.sessions(`?${sq}`)])
      .then(([d, s]) => {
        setDets(d);
        setSessions(s);
      })
      .catch((e) => setError(String(e)));
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  const completed = sessions.filter((s) => s.status === "completed");
  const inside = sessions.filter((s) => s.status === "inside");

  return (
    <div className="space-y-4 md:space-y-6">
      <header className="space-y-3">
        <div>
          <h2 className="text-xl md:text-2xl font-semibold">Lịch sử</h2>
          <p className="text-slate-400 text-sm mt-1">
            Nhận diện đã ghi · phiên vào/ra hoàn tất
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setTab("detections")}
            className={`text-sm rounded-lg px-3 py-2 border ${
              tab === "detections"
                ? "border-accent/40 bg-accent/15 text-accent"
                : "border-line hover:bg-white/5"
            }`}
          >
            Nhận diện ({dets.length})
          </button>
          <button
            type="button"
            onClick={() => setTab("sessions")}
            className={`text-sm rounded-lg px-3 py-2 border ${
              tab === "sessions"
                ? "border-accent/40 bg-accent/15 text-accent"
                : "border-line hover:bg-white/5"
            }`}
          >
            Phiên vào/ra ({completed.length}
            {inside.length ? ` · ${inside.length} trong khu vực` : ""})
          </button>
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            value={plate}
            onChange={(e) => setPlate(e.target.value)}
            placeholder="Lọc biển số"
            className="flex-1 bg-ink border border-line rounded-lg px-3 py-2.5 text-sm"
          />
          <button
            type="button"
            onClick={load}
            className="bg-accent/20 text-accent border border-accent/30 rounded-lg px-3 py-2.5 text-sm"
          >
            Lọc
          </button>
          <a
            href={tab === "sessions" ? api.exportSessionsUrl(7) : api.exportDetectionsUrl(1)}
            className="border border-line rounded-lg px-3 py-2.5 text-sm text-slate-300 hover:bg-white/5 text-center"
          >
            Xuất CSV
          </a>
        </div>
      </header>

      {error && <div className="text-danger text-sm">{error}</div>}

      {tab === "detections" ? <DetectionsList rows={dets} /> : <SessionsList rows={sessions} />}
    </div>
  );
}

function DetectionsList({ rows }: { rows: Detection[] }) {
  return (
    <>
      <div className="md:hidden space-y-2">
        {rows.map((d) => (
          <article key={d.id} className="rounded-xl border border-line bg-panel/70 p-3 text-sm flex gap-3">
            <Thumb d={d} />
            <div className="min-w-0 flex-1">
              <div className="font-mono text-lg">{d.plate_number || "Không biển"}</div>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {d.passage_direction && (
                  <span
                    className={`text-[10px] uppercase px-2 py-0.5 rounded border ${
                      d.passage_direction === "entry"
                        ? "border-ok/40 text-ok"
                        : "border-accent/40 text-accent"
                    }`}
                  >
                    {d.passage_direction === "entry" ? "Vào" : "Ra"}
                  </span>
                )}
                {d.vehicle_class && (
                  <span className="text-[10px] uppercase px-2 py-0.5 rounded border border-line text-slate-400">
                    {CLASS_LABEL[d.vehicle_class] || d.vehicle_class}
                  </span>
                )}
              </div>
              <div className="text-slate-400 mt-1 text-xs font-mono">
                {d.event_utc ? new Date(d.event_utc).toLocaleString("vi-VN") : "—"}
              </div>
              <div className="text-slate-500 text-xs mt-0.5">
                {[d.vehicle_brand, d.vehicle_color, d.event_code].filter(Boolean).join(" · ") || "—"}
              </div>
            </div>
          </article>
        ))}
        {!rows.length && (
          <div className="text-slate-500 text-sm border border-dashed border-line rounded-xl p-6 text-center">
            Chưa có nhận diện được ghi
          </div>
        )}
      </div>

      <div className="hidden md:block overflow-auto rounded-xl border border-line">
        <table className="w-full text-sm">
          <thead className="bg-panel text-slate-400 text-left">
            <tr>
              <th className="px-3 py-2">Ảnh</th>
              <th className="px-3 py-2">Biển số</th>
              <th className="px-3 py-2">Hướng</th>
              <th className="px-3 py-2">Thời gian</th>
              <th className="px-3 py-2">Xe</th>
              <th className="px-3 py-2">Sự kiện</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.id} className="border-t border-line/80">
                <td className="px-3 py-2">
                  <Thumb d={d} />
                </td>
                <td className="px-3 py-2 font-mono">{d.plate_number || "—"}</td>
                <td className="px-3 py-2">
                  {d.passage_direction === "entry"
                    ? "Vào"
                    : d.passage_direction === "exit"
                      ? "Ra"
                      : "—"}
                </td>
                <td className="px-3 py-2 font-mono text-xs">
                  {d.event_utc ? new Date(d.event_utc).toLocaleString("vi-VN") : "—"}
                </td>
                <td className="px-3 py-2 text-slate-300">
                  {[CLASS_LABEL[d.vehicle_class || ""] || d.vehicle_class, d.vehicle_brand, d.vehicle_color]
                    .filter(Boolean)
                    .join(" · ") || "—"}
                </td>
                <td className="px-3 py-2 text-slate-500 text-xs">{d.event_code || "—"}</td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-slate-500">
                  Chưa có nhận diện được ghi
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

function SessionsList({ rows }: { rows: Session[] }) {
  const statusLabel: Record<string, string> = {
    inside: "Trong khu vực",
    completed: "Hoàn tất",
    orphan_exit: "Ra (không có vào)",
  };
  return (
    <>
      <div className="md:hidden space-y-2">
        {rows.map((r) => (
          <div key={r.id} className="rounded-xl border border-line bg-panel/70 p-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <div className="font-mono text-lg">{r.plate_number}</div>
              <span className="text-[10px] uppercase px-2 py-0.5 rounded border border-line text-slate-400">
                {statusLabel[r.status] || r.status}
              </span>
            </div>
            <div className="text-slate-400 mt-1">
              Vào: {r.entered_at ? new Date(r.entered_at).toLocaleString("vi-VN") : "—"}
            </div>
            <div className="text-slate-400">
              Ra: {r.exited_at ? new Date(r.exited_at).toLocaleString("vi-VN") : "—"}
            </div>
            <div className="text-slate-300 mt-1">
              Thời gian:{" "}
              {r.duration_sec != null ? `${Math.round(r.duration_sec / 60)} phút` : "—"}
            </div>
          </div>
        ))}
        {!rows.length && (
          <div className="text-slate-500 text-sm border border-dashed border-line rounded-xl p-6 text-center">
            Chưa có phiên. Xe cần qua cổng lần 2 (≥ 60 giây) để đóng phiên vào/ra.
          </div>
        )}
      </div>

      <div className="hidden md:block overflow-auto rounded-xl border border-line">
        <table className="w-full text-sm">
          <thead className="bg-panel text-slate-400 text-left">
            <tr>
              <th className="px-3 py-2">Biển số</th>
              <th className="px-3 py-2">Trạng thái</th>
              <th className="px-3 py-2">Vào</th>
              <th className="px-3 py-2">Ra</th>
              <th className="px-3 py-2">Thời gian</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-line/80">
                <td className="px-3 py-2 font-mono">{r.plate_number}</td>
                <td className="px-3 py-2 text-slate-400">{statusLabel[r.status] || r.status}</td>
                <td className="px-3 py-2">
                  {r.entered_at ? new Date(r.entered_at).toLocaleString("vi-VN") : "—"}
                </td>
                <td className="px-3 py-2">
                  {r.exited_at ? new Date(r.exited_at).toLocaleString("vi-VN") : "—"}
                </td>
                <td className="px-3 py-2 font-mono">
                  {r.duration_sec != null ? `${Math.round(r.duration_sec / 60)} phút` : "—"}
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                  Chưa có phiên. Xe cần qua cổng lần 2 (≥ 60 giây) để đóng phiên vào/ra.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Thumb({ d }: { d: Detection }) {
  const kind =
    d.image_paths?.plate
      ? "plate"
      : d.image_paths?.vehicle
        ? "vehicle"
        : d.image_paths?.scene
          ? "scene"
          : d.image_paths
            ? Object.keys(d.image_paths)[0]
            : null;
  if (!kind) {
    return <div className="w-16 h-12 rounded-lg bg-ink border border-line shrink-0" />;
  }
  return (
    <ZoomableImage
      src={api.mediaUrl(d.id, kind)}
      alt=""
      className="w-16 h-12 object-cover rounded-lg border border-line shrink-0 bg-ink block"
    />
  );
}
