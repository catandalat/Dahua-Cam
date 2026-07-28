import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Camera, Site } from "../api";

const ROLE_LABEL: Record<string, string> = {
  entry: "Vào",
  exit: "Ra",
  bidirectional: "Hai chiều",
};

const STATUS_LABEL: Record<string, string> = {
  connected: "Đã kết nối",
  connecting: "Đang kết nối",
  disconnected: "Ngắt kết nối",
  error: "Lỗi",
  unknown: "Chưa rõ",
};

export default function CamerasPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    host: "",
    port: 80,
    username: "admin",
    password: "",
    direction_role: "bidirectional",
    site_id: "",
  });

  const refresh = async () => {
    const [c, s] = await Promise.all([api.cameras(), api.sites()]);
    setCameras(c);
    setSites(s);
    if (!form.site_id && s[0]) setForm((f) => ({ ...f, site_id: s[0].id }));
  };

  useEffect(() => {
    refresh().catch(console.error);
    const t = setInterval(() => refresh().catch(() => null), 8000);
    return () => clearInterval(t);
  }, []);

  const onCreateSite = async () => {
    const name = prompt("Tên khu vực / site?");
    if (!name) return;
    await api.createSite({ name });
    await refresh();
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setMsg(null);
    try {
      await api.createCamera({
        ...form,
        port: Number(form.port),
        enabled: true,
      });
      setForm((f) => ({ ...f, name: "", host: "", password: "" }));
      await refresh();
      setMsg("Đã thêm camera");
    } catch (err) {
      setMsg(String(err));
    }
  };

  const probe = async (id: string) => {
    try {
      const res = await api.probeCaps(id);
      setMsg(
        `Khả năng: ${res.supported_codes.length} mã sự kiện · đăng ký: ${res.suggested_subscribe.join(", ")}`,
      );
      await refresh();
    } catch (err) {
      setMsg(String(err));
    }
  };

  return (
    <div className="space-y-4 md:space-y-6">
      <header className="flex items-end justify-between gap-3">
        <div>
          <h2 className="text-xl md:text-2xl font-semibold">Camera</h2>
          <p className="text-slate-400 text-sm mt-1">
            Camera thật đang chạy · cổng HTTP 80 · bật thu sự kiện để nhận biển số realtime
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          <Link
            to="/map"
            className="border border-accent/40 text-accent rounded-lg px-3 py-2 text-sm hover:bg-accent/10"
          >
            Bản đồ
          </Link>
          <button
            type="button"
            onClick={onCreateSite}
            className="border border-line rounded-lg px-3 py-2 text-sm hover:bg-white/5"
          >
            + Khu vực
          </button>
        </div>
      </header>

      {msg && (
        <div className="text-sm text-slate-300 border border-line rounded-lg px-3 py-2 break-words">
          {msg}
        </div>
      )}

      <form
        onSubmit={onSubmit}
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 rounded-xl border border-line bg-panel/60 p-3 md:p-4"
      >
        <Field label="Tên" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
        <Field label="Địa chỉ IP / Host" value={form.host} onChange={(v) => setForm({ ...form, host: v })} />
        <Field
          label="Cổng HTTP (không dùng 554 RTSP)"
          value={String(form.port)}
          onChange={(v) => setForm({ ...form, port: Number(v) || 80 })}
        />
        <p className="text-xs text-slate-500 sm:col-span-2 lg:col-span-3 -mt-1">
          CGI snapshot / sự kiện cần cổng web (thường <span className="font-mono">80</span>).
          Cổng <span className="font-mono">554</span> là RTSP — sẽ không đọc được ảnh.
        </p>
        <Field
          label="Tài khoản"
          value={form.username}
          onChange={(v) => setForm({ ...form, username: v })}
        />
        <Field
          label="Mật khẩu"
          value={form.password}
          onChange={(v) => setForm({ ...form, password: v })}
          type="password"
        />
        <label className="text-sm space-y-1 block">
          <span className="text-slate-400">Hướng</span>
          <select
            className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
            value={form.direction_role}
            onChange={(e) => setForm({ ...form, direction_role: e.target.value })}
          >
            <option value="entry">Vào</option>
            <option value="exit">Ra</option>
            <option value="bidirectional">Hai chiều</option>
          </select>
        </label>
        <label className="text-sm space-y-1 block sm:col-span-2 lg:col-span-1">
          <span className="text-slate-400">Khu vực</span>
          <select
            className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
            value={form.site_id}
            onChange={(e) => setForm({ ...form, site_id: e.target.value })}
            required
          >
            {sites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <div className="sm:col-span-2 lg:col-span-3">
          <button
            type="submit"
            className="w-full sm:w-auto bg-accent/20 text-accent border border-accent/30 rounded-lg px-4 py-2.5 text-sm"
          >
            Thêm camera
          </button>
        </div>
      </form>

      <div className="grid gap-3">
        {cameras.map((c) => (
          <CameraCard key={c.id} camera={c} onProbe={probe} onMsg={setMsg} onRefresh={refresh} />
        ))}
        {!cameras.length && (
          <div className="text-slate-500 text-sm border border-dashed border-line rounded-xl p-6 text-center">
            Chưa có camera
          </div>
        )}
      </div>
    </div>
  );
}

function CameraCard({
  camera: c,
  onProbe,
  onMsg,
  onRefresh,
}: {
  camera: Camera;
  onProbe: (id: string) => void;
  onMsg: (m: string) => void;
  onRefresh: () => Promise<void>;
}) {
  const [rtsp, setRtsp] = useState<string | null>(null);
  const [snapKey, setSnapKey] = useState(0);

  return (
    <article className="rounded-xl border border-line bg-panel/70 p-3 md:p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-medium">{c.name}</div>
          <div className="text-sm text-slate-400 font-mono mt-1 break-all">
            {c.host}:{c.port}
          </div>
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <label className="text-xs text-slate-500">Hướng ghi nhận</label>
            <select
              className="bg-ink border border-line rounded-lg px-2 py-1.5 text-xs"
              value={c.direction_role}
              onChange={async (e) => {
                const direction_role = e.target.value;
                try {
                  await api.updateCamera(c.id, { direction_role });
                  onMsg(
                    direction_role === "bidirectional"
                      ? `«${c.name}»: Hai chiều — đã đẩy Direction=Both lên camera`
                      : `«${c.name}»: ${ROLE_LABEL[direction_role] || direction_role}`,
                  );
                  await onRefresh();
                } catch (err) {
                  onMsg(String(err));
                }
              }}
            >
              <option value="entry">Vào</option>
              <option value="exit">Ra</option>
              <option value="bidirectional">Hai chiều</option>
            </select>
          </div>
          {c.direction_role === "bidirectional" && (
            <p className="text-[11px] text-slate-500 mt-1.5">
              Hai chiều đồng bộ DetectLine camera (Both) để ghi nhận cả xe vào và xe ra.
            </p>
          )}
          <button
            type="button"
            className="mt-2 text-[11px] border border-line rounded-lg px-2 py-1 hover:bg-white/5"
            onClick={async () => {
              try {
                await api.updateCamera(c.id, { direction_role: c.direction_role });
                onMsg(`Đã đồng bộ hướng «${ROLE_LABEL[c.direction_role] || c.direction_role}» lên camera`);
              } catch (err) {
                onMsg(String(err));
              }
            }}
          >
            Đồng bộ hướng lên camera
          </button>
          {(c.port === 554 || c.port === 8554) && (
            <div className="text-xs text-amber-300 mt-2 flex flex-wrap items-center gap-2">
              Cổng {c.port} là RTSP — snapshot/sự kiện CGI sẽ lỗi.
              <button
                type="button"
                className="underline"
                onClick={async () => {
                  try {
                    await api.updateCamera(c.id, { port: 80 });
                    onMsg(`Đã đổi cổng «${c.name}» sang HTTP 80`);
                    await onRefresh();
                  } catch (e) {
                    onMsg(String(e));
                  }
                }}
              >
                Đổi sang cổng 80
              </button>
            </div>
          )}
          <div className="text-xs text-slate-500 mt-2 break-words">
            Khả năng: {(c.caps?.supported_codes || []).length} · Đăng ký sự kiện:{" "}
            {(c.subscribe_codes || []).join(", ") || "—"}
          </div>
          {c.listener_error && (
            <div className="text-xs text-danger mt-1 break-words">{c.listener_error}</div>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Status status={c.listener_status} />
          <span
            className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded border ${
              c.enabled
                ? "border-ok/40 text-ok bg-ok/10"
                : "border-line text-slate-500"
            }`}
          >
            {c.enabled ? "Đang bật" : "Đã tắt"}
          </span>
          <button
            type="button"
            className="text-xs border border-line rounded-lg px-2.5 py-1.5 hover:bg-white/5"
            onClick={async () => {
              try {
                await api.updateCamera(c.id, { enabled: !c.enabled });
                onMsg(c.enabled ? `Đã tắt «${c.name}»` : `Đã bật «${c.name}» — listener sẽ kết nối`);
                await onRefresh();
              } catch (e) {
                onMsg(String(e));
              }
            }}
          >
            {c.enabled ? "Tắt thu sự kiện" : "Bật thu sự kiện"}
          </button>
          <Link
            to={`/?camera=${c.id}`}
            className="text-xs border border-accent/40 text-accent rounded-lg px-2.5 py-1.5 hover:bg-accent/10"
          >
            Trực tiếp / kẻ vạch
          </Link>
          <button
            type="button"
            onClick={() => onProbe(c.id)}
            className="text-xs border border-line rounded-lg px-2.5 py-1.5 hover:bg-white/5"
          >
            Kiểm tra khả năng
          </button>
          <button
            type="button"
            className="text-xs border border-line rounded-lg px-2.5 py-1.5 hover:bg-white/5"
            onClick={async () => {
              const plate = prompt("Biển số giả lập?", "51F98765");
              if (!plate) return;
              try {
                const res = await api.ingestDetection({
                  camera_id: c.id,
                  plate_number: plate,
                  vehicle_brand: "Toyota",
                  vehicle_color: "White",
                  vehicle_category: "Car",
                  vehicle_class: "car",
                });
                onMsg(
                  `Đã ghi nhận ${plate} · ${Array.isArray(res.violations) ? (res.violations as string[]).join(",") || "ok" : "ok"}`,
                );
                await onRefresh();
              } catch (e) {
                onMsg(String(e));
              }
            }}
          >
            Giả lập nhận diện
          </button>
          <button
            type="button"
            className="text-xs border border-danger/40 text-danger rounded-lg px-2.5 py-1.5"
            onClick={async () => {
              if (!confirm(`Xoá camera «${c.name}»?`)) return;
              try {
                await api.deleteCamera(c.id);
                onMsg(`Đã xoá «${c.name}»`);
                await onRefresh();
              } catch (e) {
                onMsg(String(e));
              }
            }}
          >
            Xoá
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[200px_1fr] gap-3">
        <div>
          <img
            key={snapKey}
            src={`${api.snapshotUrl(c.id)}?t=${snapKey}`}
            alt="Ảnh chụp"
            className="w-full h-36 md:h-28 object-cover rounded-lg border border-line bg-ink"
            onError={(e) => {
              (e.target as HTMLImageElement).style.opacity = "0.3";
            }}
          />
          <button
            type="button"
            className="mt-2 text-xs border border-line rounded-lg px-2 py-1.5 w-full hover:bg-white/5"
            onClick={() => setSnapKey(Date.now())}
          >
            Làm mới ảnh
          </button>
        </div>
        <div className="flex flex-wrap gap-2 content-start">
          <OpBtn
            label="Chụp thủ công"
            onClick={async () => {
              await fetch(api.manualSnapUrl(c.id), { method: "POST" });
              setSnapKey(Date.now());
              onMsg("Đã chụp thủ công");
            }}
          />
          <OpBtn
            label="Bật đèn chớp"
            onClick={async () => {
              await api.strobe(c.id, "open");
              onMsg("Đã bật đèn chớp");
            }}
          />
          <OpBtn
            label="Tắt đèn chớp"
            onClick={async () => {
              await api.strobe(c.id, "close");
              onMsg("Đã tắt đèn chớp");
            }}
          />
          <OpBtn
            label="Bật phát hiện không biển"
            onClick={async () => {
              await api.setUnlicensed(c.id, true);
              onMsg("Đã bật phát hiện xe không biển");
            }}
          />
          <OpBtn
            label="Tắt phát hiện không biển"
            onClick={async () => {
              await api.setUnlicensed(c.id, false);
              onMsg("Đã tắt phát hiện xe không biển");
            }}
          />
          <OpBtn
            label="Lấy đường dẫn RTSP"
            onClick={async () => {
              const r = await api.cameraRtsp(c.id);
              setRtsp(r.rtsp_url);
              onMsg("Mở đường dẫn bằng VLC hoặc go2rtc. Trình duyệt không phát RTSP trực tiếp.");
            }}
          />
          <OpBtn
            label="Thông tin thiết bị"
            onClick={async () => {
              const r = await api.cameraDeviceInfo(c.id);
              onMsg(JSON.stringify(r.info).slice(0, 200));
            }}
          />
          <OpBtn
            label="Trạng thái bãi đỗ"
            onClick={async () => {
              try {
                const r = await api.parking(c.id);
                onMsg(`Bãi đỗ: ${JSON.stringify(r.status).slice(0, 180)}`);
              } catch (e) {
                onMsg(String(e));
              }
            }}
          />
        </div>
      </div>
      {rtsp && (
        <div className="text-xs font-mono break-all text-slate-400 border border-line rounded-lg px-2 py-2 bg-ink">
          {rtsp}
        </div>
      )}
    </article>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <label className="text-sm space-y-1 block">
      <span className="text-slate-400">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
        required={label !== "Cổng"}
      />
    </label>
  );
}

function OpBtn({
  label,
  onClick,
  onError,
}: {
  label: string;
  onClick: () => Promise<void>;
  onError?: (e: unknown) => void;
}) {
  return (
    <button
      type="button"
      className="text-xs border border-line rounded-lg px-2.5 py-1.5 hover:bg-white/5"
      onClick={() =>
        onClick().catch((e) => {
          console.error(e);
          onError?.(e);
        })
      }
    >
      {label}
    </button>
  );
}

function Status({ status }: { status: string }) {
  const color =
    status === "connected"
      ? "text-ok border-ok/40"
      : status === "error"
        ? "text-danger border-danger/40"
        : "text-slate-400 border-line";
  return (
    <span className={`text-xs px-2 py-1 rounded-lg border ${color}`}>
      {STATUS_LABEL[status] || status || "Chưa rõ"}
    </span>
  );
}
