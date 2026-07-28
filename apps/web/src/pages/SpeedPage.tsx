import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  SpeedMeasurement,
  SpeedPolicy,
  SpeedStats,
} from "../api";

export default function SpeedPage() {
  const [policies, setPolicies] = useState<SpeedPolicy[]>([]);
  const [stats, setStats] = useState<SpeedStats | null>(null);
  const [rows, setRows] = useState<SpeedMeasurement[]>([]);
  const [cameraId, setCameraId] = useState("");
  const [onlyViolations, setOnlyViolations] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [edit, setEdit] = useState<Record<string, Partial<SpeedPolicy>>>({});

  const load = async () => {
    const q = new URLSearchParams({ limit: "60" });
    if (cameraId) q.set("camera_id", cameraId);
    if (onlyViolations) q.set("only_violations", "true");
    const statsQ = cameraId ? `?hours=24&camera_id=${cameraId}` : "?hours=24";
    const [p, s, m] = await Promise.all([
      api.speedPolicies(),
      api.speedStats(statsQ),
      api.speedMeasurements(`?${q}`),
    ]);
    setPolicies(p);
    setStats(s);
    setRows(m);
  };

  useEffect(() => {
    load().catch((e) => setMsg(String(e)));
    const t = setInterval(() => load().catch(() => null), 8000);
    return () => clearInterval(t);
  }, [cameraId, onlyViolations]);

  const savePolicy = async (camera_id: string, e: FormEvent) => {
    e.preventDefault();
    const p = policies.find((x) => x.camera_id === camera_id);
    const patch = edit[camera_id] || {};
    const body = {
      min_speed: Number(patch.min_speed ?? p?.min_speed ?? 0),
      max_speed: Number(patch.max_speed ?? p?.max_speed ?? 80),
      alert_overspeed: patch.alert_overspeed ?? p?.alert_overspeed ?? true,
      alert_underspeed: patch.alert_underspeed ?? p?.alert_underspeed ?? false,
      push_to_camera: patch.push_to_camera ?? p?.push_to_camera ?? true,
    };
    try {
      const res = await api.saveSpeedPolicy(camera_id, body);
      setMsg(
        res.warning
          ? res.warning
          : `Đã lưu ngưỡng ${body.min_speed}–${body.max_speed} km/h cho ${res.camera_name}`,
      );
      setEdit((prev) => {
        const next = { ...prev };
        delete next[camera_id];
        return next;
      });
      await load();
    } catch (err) {
      setMsg(String(err));
    }
  };

  const field = (id: string, key: keyof SpeedPolicy, fallback: string | number | boolean) => {
    const p = policies.find((x) => x.camera_id === id);
    const v = edit[id]?.[key] ?? p?.[key] ?? fallback;
    return v;
  };

  return (
    <div className="space-y-4 md:space-y-6">
      <header className="space-y-1">
        <h2 className="text-xl md:text-2xl font-semibold">Tốc độ & cảnh báo</h2>
        <p className="text-slate-400 text-sm">
          Đặt ngưỡng theo camera · đo realtime · cảnh báo vượt tốc trên dashboard.
          Camera ANPR không radar (vd. ITC413) thường gửi Speed=0 — hệ thống coi là chưa đo, không
          hiện 0 km/h.
        </p>
      </header>

      {policies.some((p) => p.device_error) && (
        <div className="text-sm border border-warn/40 text-warn rounded-lg px-3 py-2">
          Một số camera không hỗ trợ CGI tốc độ (radar). Chỉ hiển thị tốc độ khi sự kiện có giá trị &gt; 0
          km/h.
        </div>
      )}
      {msg && (
        <div className="text-sm border border-line rounded-lg px-3 py-2 break-words">{msg}</div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 md:gap-3">
        <Stat label="Mẫu đo (24h)" value={stats?.samples ?? "—"} />
        <Stat label="TB tốc độ" value={stats?.avg_speed != null ? `${stats.avg_speed}` : "—"} unit="km/h" />
        <Stat label="Cao nhất" value={stats?.max_speed != null ? `${stats.max_speed}` : "—"} unit="km/h" />
        <Stat label="Vượt tốc" value={stats?.overspeed_count ?? 0} danger />
        <Stat label="Dưới tốc" value={stats?.underspeed_count ?? 0} warn />
      </div>

      <section className="space-y-3">
        <h3 className="text-sm text-slate-400 uppercase tracking-wide">Ngưỡng theo camera</h3>
        <div className="grid gap-3">
          {policies.map((p) => (
            <form
              key={p.camera_id}
              onSubmit={(e) => savePolicy(p.camera_id, e)}
              className="rounded-xl border border-line bg-panel/70 p-3 md:p-4 space-y-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="font-medium">{p.camera_name}</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {p.last_synced_at
                      ? `Đồng bộ camera: ${new Date(p.last_synced_at).toLocaleString("vi-VN")}`
                      : "Chưa đồng bộ xuống camera"}
                  </div>
                </div>
                <Link
                  to={`/?camera=${p.camera_id}`}
                  className="text-xs border border-line rounded-lg px-2.5 py-1.5"
                >
                  Trực tiếp
                </Link>
              </div>
              <div className="flex flex-wrap gap-3 items-end">
                <label className="text-sm space-y-1">
                  <span className="text-slate-500 text-xs">Tối thiểu</span>
                  <input
                    type="number"
                    min={0}
                    max={300}
                    className="w-20 block bg-ink border border-line rounded-lg px-2 py-2"
                    value={Number(field(p.camera_id, "min_speed", 0))}
                    onChange={(e) =>
                      setEdit((prev) => ({
                        ...prev,
                        [p.camera_id]: { ...prev[p.camera_id], min_speed: Number(e.target.value) },
                      }))
                    }
                  />
                </label>
                <label className="text-sm space-y-1">
                  <span className="text-slate-500 text-xs">Tối đa (km/h)</span>
                  <input
                    type="number"
                    min={1}
                    max={300}
                    className="w-20 block bg-ink border border-line rounded-lg px-2 py-2"
                    value={Number(field(p.camera_id, "max_speed", 80))}
                    onChange={(e) =>
                      setEdit((prev) => ({
                        ...prev,
                        [p.camera_id]: { ...prev[p.camera_id], max_speed: Number(e.target.value) },
                      }))
                    }
                  />
                </label>
                <label className="flex items-center gap-2 text-sm pb-2">
                  <input
                    type="checkbox"
                    checked={Boolean(field(p.camera_id, "alert_overspeed", true))}
                    onChange={(e) =>
                      setEdit((prev) => ({
                        ...prev,
                        [p.camera_id]: { ...prev[p.camera_id], alert_overspeed: e.target.checked },
                      }))
                    }
                  />
                  Cảnh báo vượt tốc
                </label>
                <label className="flex items-center gap-2 text-sm pb-2">
                  <input
                    type="checkbox"
                    checked={Boolean(field(p.camera_id, "alert_underspeed", false))}
                    onChange={(e) =>
                      setEdit((prev) => ({
                        ...prev,
                        [p.camera_id]: { ...prev[p.camera_id], alert_underspeed: e.target.checked },
                      }))
                    }
                  />
                  Cảnh báo dưới tốc
                </label>
                <label className="flex items-center gap-2 text-sm pb-2">
                  <input
                    type="checkbox"
                    checked={Boolean(field(p.camera_id, "push_to_camera", true))}
                    onChange={(e) =>
                      setEdit((prev) => ({
                        ...prev,
                        [p.camera_id]: { ...prev[p.camera_id], push_to_camera: e.target.checked },
                      }))
                    }
                  />
                  Đẩy xuống camera
                </label>
                <button
                  type="submit"
                  className="text-sm bg-accent/20 text-accent border border-accent/30 rounded-lg px-3 py-2"
                >
                  Lưu ngưỡng
                </button>
              </div>
            </form>
          ))}
          {!policies.length && (
            <div className="text-sm text-slate-500 border border-dashed border-line rounded-xl p-6 text-center">
              Chưa có camera
            </div>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <h3 className="text-sm text-slate-400 uppercase tracking-wide">Đo gần đây</h3>
          <div className="flex flex-wrap gap-2">
            <select
              className="bg-ink border border-line rounded-lg px-3 py-2 text-sm"
              value={cameraId}
              onChange={(e) => setCameraId(e.target.value)}
            >
              <option value="">Tất cả camera</option>
              {policies.map((p) => (
                <option key={p.camera_id} value={p.camera_id}>
                  {p.camera_name}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-2 text-sm border border-line rounded-lg px-3 py-2">
              <input
                type="checkbox"
                checked={onlyViolations}
                onChange={(e) => setOnlyViolations(e.target.checked)}
              />
              Chỉ vượt / dưới tốc
            </label>
          </div>
        </div>

        <div className="grid gap-2">
          {rows.map((r) => (
            <article
              key={r.id}
              className={`flex gap-3 items-center rounded-xl border p-3 ${
                r.status === "overspeed"
                  ? "border-danger/40 bg-danger/10"
                  : r.status === "underspeed"
                    ? "border-warn/40 bg-warn/10"
                    : "border-line bg-panel/70"
              }`}
            >
              {r.image_paths ? (
                <img
                  src={api.mediaUrl(
                    r.id,
                    r.image_paths.overspeed
                      ? "overspeed"
                      : r.image_paths.plate
                        ? "plate"
                        : r.image_paths.vehicle
                          ? "vehicle"
                          : Object.keys(r.image_paths)[0],
                  )}
                  alt=""
                  className="w-16 h-12 object-cover rounded-lg border border-line bg-ink shrink-0"
                />
              ) : (
                <div className="w-16 h-12 rounded-lg border border-line bg-ink shrink-0" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-base">{r.plate_number || "—"}</span>
                  <span
                    className={`font-mono text-sm ${
                      r.status === "overspeed"
                        ? "text-danger"
                        : r.status === "underspeed"
                          ? "text-warn"
                          : "text-accent"
                    }`}
                  >
                    {r.speed} km/h
                  </span>
                  {r.limit_max != null && (
                    <span className="text-xs text-slate-500">
                      ngưỡng {r.limit_min ?? 0}–{r.limit_max}
                    </span>
                  )}
                  {r.status === "overspeed" && (
                    <span className="text-[10px] uppercase tracking-wide text-danger border border-danger/30 px-2 py-0.5 rounded">
                      Vượt tốc{r.over_pct != null ? ` +${r.over_pct}%` : ""}
                    </span>
                  )}
                  {r.status === "underspeed" && (
                    <span className="text-[10px] uppercase tracking-wide text-warn border border-warn/30 px-2 py-0.5 rounded">
                      Dưới tốc
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  {r.camera_name || "—"} ·{" "}
                  {r.event_utc ? new Date(r.event_utc).toLocaleString("vi-VN") : "—"}
                </div>
              </div>
            </article>
          ))}
          {!rows.length && (
            <div className="text-slate-500 text-sm border border-dashed border-line rounded-xl p-6 text-center">
              Chưa có mẫu đo tốc độ
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  unit,
  danger,
  warn,
}: {
  label: string;
  value: string | number;
  unit?: string;
  danger?: boolean;
  warn?: boolean;
}) {
  return (
    <div className="rounded-xl border border-line bg-panel/70 px-3 py-3">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div
        className={`text-xl md:text-2xl font-semibold mt-1 font-mono ${
          danger ? "text-danger" : warn ? "text-warn" : ""
        }`}
      >
        {value}
        {unit && <span className="text-xs text-slate-500 font-sans ml-1">{unit}</span>}
      </div>
    </div>
  );
}
