import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { api, Camera, OverlayShape, WS_URL } from "../api";

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

type LiveDet = {
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

/** Dahua 0–8192 ↔ canvas pixel */
function toCanvas(pt: number[], w: number, h: number): [number, number] {
  return [(pt[0] / 8192) * w, (pt[1] / 8192) * h];
}
function toDahua(x: number, y: number, w: number, h: number): [number, number] {
  return [
    Math.max(0, Math.min(8192, Math.round((x / w) * 8192))),
    Math.max(0, Math.min(8192, Math.round((y / h) * 8192))),
  ];
}

export default function MonitorPage() {
  const [searchParams] = useSearchParams();
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [cameraId, setCameraId] = useState(searchParams.get("camera") || "");
  const [tool, setTool] = useState<Tool>("lane_line");
  const [shapes, setShapes] = useState<OverlayShape[]>([]);
  const [draftPts, setDraftPts] = useState<number[][]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [live, setLive] = useState(true);
  const [intervalMs, setIntervalMs] = useState(1500);
  const [snapKey, setSnapKey] = useState(0);
  const [snapError, setSnapError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [dets, setDets] = useState<LiveDet[]>([]);
  const [showDets, setShowDets] = useState(true);
  const [label, setLabel] = useState("");

  const imgRef = useRef<HTMLImageElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [viewSize, setViewSize] = useState({ w: 0, h: 0 });

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
    api
      .getOverlay(cameraId)
      .then((o) => setShapes(o.shapes || []))
      .catch((e) => setMsg(String(e)));
    api
      .liveDetections(cameraId, 15)
      .then(setDets)
      .catch(() => null);
  }, [cameraId]);

  // Snapshot refresh
  useEffect(() => {
    if (!live || !cameraId) return;
    const t = setInterval(() => setSnapKey(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [live, cameraId, intervalMs]);

  // WS detections for selected camera
  useEffect(() => {
    if (!cameraId) return;
    const ws = new WebSocket(WS_URL);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "detection" && msg.detection?.camera_id === cameraId) {
          const d = msg.detection;
          const meta = d.meta || {};
          setDets((prev) =>
            [
              {
                id: d.id,
                plate_number: d.plate_number,
                plate_bbox: meta.plate_bbox,
                vehicle_bbox: meta.vehicle_bbox,
                vehicle_class: d.vehicle_class,
                speed: d.speed,
                event_utc: d.event_utc,
              },
              ...prev,
            ].slice(0, 20),
          );
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
  }, [cameraId]);

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
        s.id === selectedId
          ? "#ffffff"
          : s.color || SHAPE_COLOR[s.type] || "#3d9cf0";
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

      // points
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
      for (const d of dets.slice(0, 8)) {
        const box = d.vehicle_bbox || d.plate_bbox;
        if (!box || box.length < 4) continue;
        // Dahua bbox often [x1,y1,x2,y2] in 0-8192
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
  }, [shapes, draftPts, tool, selectedId, dets, showDets]);

  useEffect(() => {
    draw();
  }, [draw, viewSize]);

  const onCanvasClick = (e: MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || !cameraId) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const dahua = toDahua(x, y, canvas.width, canvas.height);

    if (tool === "select") {
      // pick nearest shape vertex / line
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

    // region: accumulate until double-click handled separately;  click adds
    setDraftPts(next);
  };

  const onCanvasDblClick = () => {
    if (tool !== "region" || draftPts.length < 3) return;
    commitShape("region", draftPts);
    setDraftPts([]);
  };

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

  const undoDraft = () => setDraftPts((p) => p.slice(0, -1));

  const snapUrl = useMemo(
    () => (cameraId ? `${api.snapshotUrl(cameraId)}?t=${snapKey}` : ""),
    [cameraId, snapKey],
  );

  return (
    <div className="space-y-4 md:space-y-5">
      <header className="space-y-2">
        <h2 className="text-xl md:text-2xl font-semibold">Quan sát & kẻ vạch</h2>
        <p className="text-slate-400 text-sm">
          Xem realtime từ camera · vẽ vạch làn / vạch dừng / vùng phát hiện (toạ độ Dahua 0–8192)
        </p>
      </header>

      {msg && (
        <div className="text-sm border border-line rounded-lg px-3 py-2 break-words">{msg}</div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
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
          </div>

          <div
            ref={wrapRef}
            className="relative w-full rounded-xl border border-line bg-ink overflow-hidden select-none"
          >
            {cameraId ? (
              <>
                <img
                  ref={imgRef}
                  src={snapUrl}
                  alt="Quan sát camera"
                  className="w-full h-auto block max-h-[70vh] object-contain bg-black"
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
                  className="absolute inset-0 w-full h-full cursor-crosshair"
                  onClick={onCanvasClick}
                  onDoubleClick={onCanvasDblClick}
                />
              </>
            ) : (
              <div className="h-64 flex items-center justify-center text-slate-500 text-sm">
                Chọn camera để quan sát
              </div>
            )}
          </div>

          <p className="text-xs text-slate-500">
            Vạch làn / dừng: bấm 2 điểm. Vùng phát hiện: bấm nhiều điểm, nháy đúp để kết thúc.
            Toạ độ lưu theo chuẩn camera (0–8192).
          </p>
        </div>

        <aside className="space-y-3">
          <div className="rounded-xl border border-line bg-panel/70 p-3 space-y-2">
            <div className="text-sm text-slate-400">Công cụ kẻ vạch</div>
            {(Object.keys(TOOL_LABEL) as Tool[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => {
                  setTool(t);
                  setDraftPts([]);
                }}
                className={`w-full text-left text-sm rounded-lg px-3 py-2 border ${
                  tool === t
                    ? "border-accent/40 bg-accent/15 text-accent"
                    : "border-line hover:bg-white/5"
                }`}
              >
                {TOOL_LABEL[t]}
              </button>
            ))}
            <label className="block text-sm space-y-1 pt-1">
              <span className="text-slate-500 text-xs">Nhãn vạch mới</span>
              <input
                className="w-full bg-ink border border-line rounded-lg px-3 py-2"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="Làn 1 / Vạch dừng…"
              />
            </label>
            <div className="flex flex-wrap gap-2 pt-1">
              <button
                type="button"
                className="text-xs border border-line rounded-lg px-2.5 py-1.5"
                onClick={undoDraft}
                disabled={!draftPts.length}
              >
                Hoàn tác điểm
              </button>
              <button
                type="button"
                className="text-xs border border-line rounded-lg px-2.5 py-1.5 text-danger"
                onClick={removeSelected}
                disabled={!selectedId}
              >
                Xoá vạch chọn
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-line bg-panel/70 p-3 space-y-2">
            <div className="text-sm text-slate-400">Quan sát realtime</div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
              Tự làm mới ảnh
            </label>
            <label className="block text-sm space-y-1">
              <span className="text-slate-500 text-xs">Chu kỳ (ms)</span>
              <select
                className="w-full bg-ink border border-line rounded-lg px-3 py-2"
                value={intervalMs}
                onChange={(e) => setIntervalMs(Number(e.target.value))}
              >
                <option value={800}>800 ms</option>
                <option value={1500}>1,5 giây</option>
                <option value={3000}>3 giây</option>
                <option value={5000}>5 giây</option>
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={showDets}
                onChange={(e) => setShowDets(e.target.checked)}
              />
              Hiện khung xe / biển nhận diện
            </label>
          </div>

          <div className="rounded-xl border border-line bg-panel/70 p-3 space-y-2">
            <div className="text-sm text-slate-400">Danh sách vạch ({shapes.length})</div>
            <div className="max-h-40 overflow-auto space-y-1">
              {shapes.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setSelectedId(s.id)}
                  className={`w-full text-left text-xs rounded-lg px-2 py-1.5 border ${
                    selectedId === s.id ? "border-accent/40 bg-accent/10" : "border-line"
                  }`}
                >
                  <span
                    className="inline-block w-2 h-2 rounded-full mr-2"
                    style={{ background: SHAPE_COLOR[s.type] }}
                  />
                  {s.label || TOOL_LABEL[s.type]} · {s.points.length} điểm
                </button>
              ))}
              {!shapes.length && (
                <div className="text-xs text-slate-500">Chưa có vạch</div>
              )}
            </div>
            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={save}
                className="flex-1 text-sm bg-accent/20 text-accent border border-accent/30 rounded-lg px-3 py-2"
              >
                Lưu
              </button>
              <button
                type="button"
                onClick={clearAll}
                className="text-sm border border-danger/40 text-danger rounded-lg px-3 py-2"
              >
                Xoá hết
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-line bg-panel/70 p-3">
            <div className="text-sm text-slate-400 mb-2">Nhận diện gần đây</div>
            <div className="space-y-1 max-h-48 overflow-auto text-sm">
              {dets.map((d) => (
                <div key={d.id} className="flex justify-between gap-2 border-b border-line/50 py-1">
                  <span className="font-mono">{d.plate_number || "—"}</span>
                  <span className="text-xs text-accent font-mono shrink-0">
                    {d.speed != null ? `${d.speed} km/h` : "—"}
                  </span>
                  <span className="text-xs text-slate-500 shrink-0">
                    {d.event_utc ? new Date(d.event_utc).toLocaleTimeString("vi-VN") : ""}
                  </span>
                </div>
              ))}
              {!dets.length && (
                <div className="text-xs text-slate-500">Chưa có nhận diện</div>
              )}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
