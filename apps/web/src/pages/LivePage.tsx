import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { useSearchParams } from "react-router-dom";
import {
  api,
  Camera,
  Detection,
  OverlayShape,
  Overview,
  WS_URL,
} from "../api";
import { ZoomableImage } from "../components/ZoomableImage";

type Tool = "lane_line" | "stop_line" | "region" | "select";

const TOOL_LABEL: Record<Tool, string> = {
  select: "Chọn / sửa",
  lane_line: "Vạch làn",
  stop_line: "Vạch dừng",
  region: "Vùng phát hiện",
};

const SHAPE_COLOR: Record<string, string> = {
  lane_line: "#3d9cf0",
  stop_line: "#e8a838",
  region: "#3ecf8e",
};

const CLASS_LABEL: Record<string, string> = {
  car: "Ô tô",
  motorcycle: "Xe máy",
  other: "Khác",
  unknown: "Chưa rõ",
};

type OverlayDet = {
  id: string;
  plate_number?: string;
  plate_bbox?: number[];
  vehicle_bbox?: number[];
  vehicle_class?: string;
  speed?: number;
  event_utc?: string;
};

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

function toCanvas(pt: number[], w: number, h: number): [number, number] {
  return [(pt[0] / 8192) * w, (pt[1] / 8192) * h];
}
function toDahua(x: number, y: number, w: number, h: number): [number, number] {
  return [
    Math.max(0, Math.min(8192, Math.round((x / w) * 8192))),
    Math.max(0, Math.min(8192, Math.round((y / h) * 8192))),
  ];
}

export default function LivePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [cameraId, setCameraId] = useState(searchParams.get("camera") || "");
  const [tool, setTool] = useState<Tool>("select");
  const [shapes, setShapes] = useState<OverlayShape[]>([]);
  const [draftPts, setDraftPts] = useState<number[][]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [liveSnap, setLiveSnap] = useState(true);
  const [intervalMs, setIntervalMs] = useState(1500);
  const [snapKey, setSnapKey] = useState(0);
  const [snapError, setSnapError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [overlayDets, setOverlayDets] = useState<OverlayDet[]>([]);
  const [showDets, setShowDets] = useState(true);
  const [label, setLabel] = useState("");
  const [drawMode, setDrawMode] = useState(false);

  const [items, setItems] = useState<Detection[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [vehicleClass, setVehicleClass] = useState("");
  const [brand, setBrand] = useState("");
  const [color, setColor] = useState("");
  const [onlyThisCam, setOnlyThisCam] = useState(true);

  const imgRef = useRef<HTMLImageElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [viewSize, setViewSize] = useState({ w: 0, h: 0 });

  const query = useMemo(() => {
    const q = new URLSearchParams({ limit: "40" });
    if (vehicleClass) q.set("vehicle_class", vehicleClass);
    if (brand.trim()) q.set("vehicle_brand", brand.trim());
    if (color.trim()) q.set("vehicle_color", color.trim());
    if (onlyThisCam && cameraId) q.set("camera_id", cameraId);
    return `?${q}`;
  }, [vehicleClass, brand, color, onlyThisCam, cameraId]);

  const loadFeed = useCallback(
    () =>
      api
        .detections(query)
        .then(setItems)
        .catch((e) => setError(String(e))),
    [query],
  );

  useEffect(() => {
    api.cameras().then((c) => {
      setCameras(c);
      const fromQuery = searchParams.get("camera");
      if (fromQuery && c.some((x) => x.id === fromQuery)) {
        setCameraId(fromQuery);
      } else if (!cameraId && c[0]) {
        setCameraId(c[0].id);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!cameraId) return;
    const next = new URLSearchParams(searchParams);
    if (next.get("camera") !== cameraId) {
      next.set("camera", cameraId);
      setSearchParams(next, { replace: true });
    }
  }, [cameraId, searchParams, setSearchParams]);

  useEffect(() => {
    if (!cameraId) return;
    api
      .getOverlay(cameraId)
      .then((o) => setShapes(o.shapes || []))
      .catch((e) => setMsg(String(e)));
    api
      .liveDetections(cameraId, 3)
      .then((rows) =>
        setOverlayDets(
          rows
            .filter((d) => d.plate_number && (d.plate_bbox || d.vehicle_bbox))
            .map((d) => ({
              id: d.id,
              plate_number: d.plate_number,
              plate_bbox: d.plate_bbox,
              vehicle_bbox: d.vehicle_bbox,
              vehicle_class: d.vehicle_class,
              event_utc: d.event_utc,
            })),
        ),
      )
      .catch(() => setOverlayDets([]));
  }, [cameraId]);

  // Expire overlay boxes so they don't linger as "viền ảo" on newer snapshots
  useEffect(() => {
    const t = setInterval(() => {
      const cutoff = Date.now() - 12_000;
      setOverlayDets((prev) =>
        prev.filter((d) => {
          if (!d.event_utc) return false;
          const ts = Date.parse(d.event_utc);
          return Number.isFinite(ts) && ts >= cutoff;
        }),
      );
    }, 2000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!liveSnap || !cameraId) return;
    const t = setInterval(() => setSnapKey(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [liveSnap, cameraId, intervalMs]);

  useEffect(() => {
    loadFeed();
    api.overview().then(setOverview).catch(() => null);

    const ws = new WebSocket(WS_URL);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type !== "detection" || !msg.detection) return;
        const d = msg.detection as Detection;
        const meta = (d as Detection & { meta?: Record<string, unknown> }).meta || {};

        if (!cameraId || d.camera_id === cameraId) {
          if (d.plate_number && (meta.plate_bbox || meta.vehicle_bbox)) {
            setOverlayDets((prev) =>
              [
                {
                  id: d.id,
                  plate_number: d.plate_number,
                  plate_bbox: meta.plate_bbox as number[] | undefined,
                  vehicle_bbox: meta.vehicle_bbox as number[] | undefined,
                  vehicle_class: d.vehicle_class,
                  speed: d.speed,
                  event_utc: d.event_utc,
                },
                ...prev.filter((x) => x.id !== d.id),
              ].slice(0, 2),
            );
          }
        }

        const okCam = !onlyThisCam || !cameraId || d.camera_id === cameraId;
        const okClass = !vehicleClass || d.vehicle_class === vehicleClass;
        const okBrand =
          !brand.trim() ||
          (d.vehicle_brand || "").toLowerCase().includes(brand.trim().toLowerCase());
        const okColor =
          !color.trim() ||
          (d.vehicle_color || "").toLowerCase() === color.trim().toLowerCase();
        if (okCam && okClass && okBrand && okColor) {
          setItems((prev) => [d, ...prev].slice(0, 80));
        }
        api.overview().then(setOverview).catch(() => null);
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
  }, [query, vehicleClass, brand, color, onlyThisCam, cameraId, loadFeed]);

  const resizeCanvas = useCallback(() => {
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (!img || !canvas) return;
    const w = img.clientWidth;
    const h = img.clientHeight;
    if (w <= 0 || h <= 0) return;
    canvas.width = w;
    canvas.height = h;
    setViewSize({ w, h });
  }, []);

  useEffect(() => {
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);
    return () => window.removeEventListener("resize", resizeCanvas);
  }, [resizeCanvas, snapKey, cameraId]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const { w, h } = { w: canvas.width, h: canvas.height };
    ctx.clearRect(0, 0, w, h);

    const allShapes = [...shapes];
    if (draftPts.length) {
      allShapes.push({
        id: "__draft",
        type: tool === "select" ? "lane_line" : tool,
        label: "",
        points: draftPts,
      });
    }

    for (const s of allShapes) {
      const color =
        s.id === selectedId ? "#ffffff" : s.color || SHAPE_COLOR[s.type] || "#3d9cf0";
      const pts = s.points.map((p) => toCanvas(p, w, h));
      if (pts.length < 1) continue;

      ctx.strokeStyle = color;
      ctx.fillStyle = color + "33";
      ctx.lineWidth = s.type === "stop_line" ? 3 : 2;
      ctx.setLineDash(s.id === "__draft" ? [6, 4] : []);

      ctx.beginPath();
      ctx.moveTo(pts[0][0], pts[0][1]);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
      if (s.type === "region" && pts.length >= 3) {
        ctx.closePath();
        ctx.fill();
      }
      ctx.stroke();
      ctx.setLineDash([]);

      for (const [x, y] of pts) {
        ctx.beginPath();
        ctx.fillStyle = color;
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.fill();
      }

      if (s.label) {
        ctx.fillStyle = "#e2e8f0";
        ctx.font = "12px IBM Plex Sans, sans-serif";
        ctx.fillText(s.label, pts[0][0] + 6, pts[0][1] - 6);
      }
    }

    if (showDets) {
      // Only freshest box — prefer plate; avoid stacking stale vehicle frames
      for (const d of overlayDets.slice(0, 1)) {
        const box = d.plate_bbox || d.vehicle_bbox;
        if (!box || box.length < 4) continue;
        const [x1, y1] = toCanvas([box[0], box[1]], w, h);
        const [x2, y2] = toCanvas([box[2], box[3]], w, h);
        ctx.strokeStyle = "#e85d4c";
        ctx.lineWidth = 2;
        ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
        ctx.fillStyle = "#e85d4c";
        ctx.font = "bold 13px IBM Plex Mono, monospace";
        ctx.fillText(d.plate_number || "?", x1, Math.max(14, y1 - 4));
      }
    }
  }, [shapes, draftPts, tool, selectedId, overlayDets, showDets]);

  useEffect(() => {
    draw();
  }, [draw, viewSize]);

  const commitShape = (type: OverlayShape["type"], points: number[][]) => {
    const shape: OverlayShape = {
      id: uid(),
      type,
      label: label.trim() || TOOL_LABEL[type],
      points,
      color: SHAPE_COLOR[type],
    };
    setShapes((prev) => [...prev, shape]);
    setSelectedId(shape.id);
    setLabel("");
  };

  const onCanvasClick = (e: MouseEvent<HTMLCanvasElement>) => {
    if (!drawMode) return;
    const canvas = canvasRef.current;
    if (!canvas || !cameraId) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const dahua = toDahua(x, y, canvas.width, canvas.height);

    if (tool === "select") {
      let best: string | null = null;
      let bestDist = 24;
      for (const s of shapes) {
        for (const p of s.points) {
          const [cx, cy] = toCanvas(p, canvas.width, canvas.height);
          const dist = Math.hypot(cx - x, cy - y);
          if (dist < bestDist) {
            bestDist = dist;
            best = s.id;
          }
        }
      }
      setSelectedId(best);
      return;
    }

    const next = [...draftPts, dahua];
    if (tool === "lane_line" || tool === "stop_line") {
      if (next.length >= 2) {
        commitShape(tool, next);
        setDraftPts([]);
      } else {
        setDraftPts(next);
      }
      return;
    }
    setDraftPts(next);
  };

  const onCanvasDblClick = () => {
    if (!drawMode || tool !== "region" || draftPts.length < 3) return;
    commitShape("region", draftPts);
    setDraftPts([]);
  };

  const removeSelected = () => {
    if (!selectedId) return;
    setShapes((prev) => prev.filter((s) => s.id !== selectedId));
    setSelectedId(null);
  };

  const clearAll = () => {
    if (!confirm("Xoá toàn bộ vạch trên camera này?")) return;
    setShapes([]);
    setDraftPts([]);
    setSelectedId(null);
  };

  const save = async () => {
    if (!cameraId) return;
    try {
      await api.saveOverlay(cameraId, { shapes, enabled: true });
      setMsg("Đã lưu vạch quan sát");
    } catch (e) {
      setMsg(String(e));
    }
  };

  const snapUrl = useMemo(
    () => (cameraId ? `${api.snapshotUrl(cameraId)}?t=${snapKey}` : ""),
    [cameraId, snapKey],
  );

  return (
    <div className="space-y-4 md:space-y-5">
      <header className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl md:text-2xl font-semibold">Trực tiếp</h2>
          <p className="text-slate-400 text-sm mt-1">
            Camera realtime · kẻ vạch ghi nhận · nhận diện thời gian thực
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

      {msg && (
        <div className="text-sm border border-line rounded-lg px-3 py-2 break-words">{msg}</div>
      )}
      {error && <div className="text-danger text-sm">{error}</div>}

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.9fr)] gap-4">
        {/* Camera + overlay */}
        <div className="space-y-3 min-w-0">
          <div className="flex flex-col sm:flex-row gap-2">
            <select
              className="flex-1 bg-ink border border-line rounded-lg px-3 py-2.5 text-sm"
              value={cameraId}
              onChange={(e) => {
                setCameraId(e.target.value);
                setDraftPts([]);
                setSelectedId(null);
              }}
            >
              {!cameras.length && <option value="">Chưa có camera</option>}
              {cameras.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.host})
                </option>
              ))}
            </select>
            <button
              type="button"
              className="border border-line rounded-lg px-3 py-2.5 text-sm"
              onClick={() => setSnapKey(Date.now())}
            >
              Chụp ngay
            </button>
            <button
              type="button"
              className={`border rounded-lg px-3 py-2.5 text-sm ${
                drawMode
                  ? "border-accent/40 bg-accent/15 text-accent"
                  : "border-line hover:bg-white/5"
              }`}
              onClick={() => {
                setDrawMode((v) => !v);
                setDraftPts([]);
                if (!drawMode) setTool("lane_line");
                else setTool("select");
              }}
            >
              {drawMode ? "Đang kẻ vạch" : "Kẻ vạch"}
            </button>
          </div>

          <div className="relative w-full rounded-xl border border-line bg-ink overflow-hidden select-none">
            {cameraId ? (
              <>
                <img
                  ref={imgRef}
                  src={snapUrl}
                  alt="Camera trực tiếp"
                  className="w-full h-auto block max-h-[62vh] object-contain bg-black"
                  onLoad={() => {
                    setSnapError(null);
                    resizeCanvas();
                  }}
                  onError={async () => {
                    try {
                      const r = await fetch(snapUrl);
                      const text = await r.text();
                      let detail = text.slice(0, 200);
                      try {
                        detail = JSON.parse(text).detail || detail;
                      } catch {
                        /* keep raw */
                      }
                      setSnapError(
                        r.status === 502
                          ? `Không đọc được ảnh camera (${r.status}): ${detail}. Kiểm tra cổng HTTP (80), IP và mật khẩu — không dùng cổng RTSP 554.`
                          : `Lỗi ảnh (${r.status}): ${detail}`,
                      );
                    } catch {
                      setSnapError("Không tải được snapshot từ API");
                    }
                  }}
                  draggable={false}
                />
                {snapError && (
                  <div className="absolute inset-x-0 bottom-0 bg-red-950/90 text-red-100 text-xs md:text-sm px-3 py-2 border-t border-red-800">
                    {snapError}
                  </div>
                )}
                <canvas
                  ref={canvasRef}
                  className={`absolute inset-0 w-full h-full ${
                    drawMode ? "cursor-crosshair" : "pointer-events-none"
                  }`}
                  onClick={onCanvasClick}
                  onDoubleClick={onCanvasDblClick}
                />
              </>
            ) : (
              <div className="h-64 flex items-center justify-center text-slate-500 text-sm">
                Chọn camera để xem trực tiếp
              </div>
            )}
          </div>

          {drawMode && (
            <div className="rounded-xl border border-line bg-panel/70 p-3 space-y-3">
              <div className="flex flex-wrap gap-2">
                {(Object.keys(TOOL_LABEL) as Tool[]).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => {
                      setTool(t);
                      setDraftPts([]);
                    }}
                    className={`text-sm rounded-lg px-3 py-1.5 border ${
                      tool === t
                        ? "border-accent/40 bg-accent/15 text-accent"
                        : "border-line hover:bg-white/5"
                    }`}
                  >
                    {TOOL_LABEL[t]}
                  </button>
                ))}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-2">
                <input
                  className="w-full bg-ink border border-line rounded-lg px-3 py-2 text-sm"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="Nhãn vạch mới (Làn 1 / Vạch dừng…)"
                />
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="text-xs border border-line rounded-lg px-2.5 py-2"
                    onClick={() => setDraftPts((p) => p.slice(0, -1))}
                    disabled={!draftPts.length}
                  >
                    Hoàn tác
                  </button>
                  <button
                    type="button"
                    className="text-xs border border-danger/40 text-danger rounded-lg px-2.5 py-2"
                    onClick={removeSelected}
                    disabled={!selectedId}
                  >
                    Xoá chọn
                  </button>
                  <button
                    type="button"
                    onClick={save}
                    className="text-xs bg-accent/20 text-accent border border-accent/30 rounded-lg px-2.5 py-2"
                  >
                    Lưu vạch
                  </button>
                  <button
                    type="button"
                    onClick={clearAll}
                    className="text-xs border border-danger/40 text-danger rounded-lg px-2.5 py-2"
                  >
                    Xoá hết
                  </button>
                </div>
              </div>
              <p className="text-xs text-slate-500">
                Vạch làn / dừng: bấm 2 điểm. Vùng: nhiều điểm, nháy đúp kết thúc. Chỉ ghi nhận xe gần
                vạch hoặc trong vùng đã lưu.
              </p>
              {shapes.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {shapes.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => setSelectedId(s.id)}
                      className={`text-xs rounded-lg px-2 py-1 border ${
                        selectedId === s.id ? "border-accent/40 bg-accent/10" : "border-line"
                      }`}
                    >
                      <span
                        className="inline-block w-2 h-2 rounded-full mr-1.5"
                        style={{ background: SHAPE_COLOR[s.type] }}
                      />
                      {s.label || TOOL_LABEL[s.type]}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-slate-400">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={liveSnap}
                onChange={(e) => setLiveSnap(e.target.checked)}
              />
              Tự làm mới ảnh
            </label>
            <label className="flex items-center gap-2">
              <span className="text-xs text-slate-500">Chu kỳ</span>
              <select
                className="bg-ink border border-line rounded-lg px-2 py-1 text-sm"
                value={intervalMs}
                onChange={(e) => setIntervalMs(Number(e.target.value))}
              >
                <option value={800}>800 ms</option>
                <option value={1500}>1,5 giây</option>
                <option value={3000}>3 giây</option>
                <option value={5000}>5 giây</option>
              </select>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={showDets}
                onChange={(e) => setShowDets(e.target.checked)}
              />
              Hiện khung biển (chỉ vài giây sau nhận diện)
            </label>
          </div>
        </div>

        {/* Live feed */}
        <div className="space-y-3 min-w-0">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
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
            <div className="flex flex-col justify-end gap-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={onlyThisCam}
                  onChange={(e) => setOnlyThisCam(e.target.checked)}
                />
                Chỉ camera đang xem
              </label>
              <button
                type="button"
                className="w-full text-sm border border-line rounded-lg px-3 py-2.5 hover:bg-white/5"
                onClick={() => loadFeed()}
              >
                Áp dụng lọc
              </button>
            </div>
          </div>

          <div className="grid gap-2 max-h-[70vh] overflow-auto pr-0.5">
            {items.map((d) => (
              <article
                key={d.id}
                className="flex gap-3 rounded-xl border border-line bg-panel/70 p-3 items-start"
              >
                <Thumb detection={d} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-base tracking-wide">
                      {d.plate_number ||
                        (d.vehicle_class === "motorcycle"
                          ? "Xe máy (không biển)"
                          : d.vehicle_class === "car"
                            ? "Ô tô (không biển)"
                            : d.vehicle_category || "Không biển")}
                    </span>
                    {d.vehicle_class && (
                      <Badge
                        color={d.vehicle_class === "motorcycle" ? "warn" : "accent"}
                        text={CLASS_LABEL[d.vehicle_class] || d.vehicle_class}
                      />
                    )}
                    {d.vehicle_color &&
                      String(d.vehicle_color).toLowerCase() !== "unknown" && (
                        <Badge color="ok" text={String(d.vehicle_color)} />
                      )}
                    {!d.vehicle_color &&
                      d.plate_color &&
                      String(d.plate_color).toLowerCase() !== "unknown" && (
                        <Badge color="ok" text={`Biển ${d.plate_color}`} />
                      )}
                    {!d.vehicle_color &&
                      !d.plate_color &&
                      d.meta &&
                      typeof d.meta.plate_color === "string" &&
                      d.meta.plate_color &&
                      String(d.meta.plate_color).toLowerCase() !== "unknown" && (
                        <Badge color="ok" text={`Biển ${d.meta.plate_color}`} />
                      )}
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
                  </div>
                  <div className="text-sm text-slate-400 mt-1 break-words">
                    {[
                      d.vehicle_brand,
                      d.vehicle_model,
                      d.vehicle_category,
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
                Chưa có sự kiện. Kiểm tra camera và bộ thu sự kiện.
              </div>
            )}
          </div>
        </div>
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
    return <div className="w-20 h-14 rounded-lg bg-ink border border-line shrink-0" />;
  }
  return (
    <ZoomableImage
      src={api.mediaUrl(detection.id, kind)}
      alt=""
      className="w-20 h-14 object-cover rounded-lg border border-line shrink-0 bg-ink block"
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
    <span
      className={`text-[10px] md:text-[11px] uppercase tracking-wide px-2 py-0.5 rounded border ${map[color]}`}
    >
      {text}
    </span>
  );
}
