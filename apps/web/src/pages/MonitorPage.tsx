import { Navigate, useSearchParams } from "react-router-dom";

/** Legacy /monitor → Trực tiếp (gộp quan sát + live) */
export default function MonitorPage() {
  const [params] = useSearchParams();
  const q = params.toString();
  return <Navigate to={q ? `/?${q}` : "/"} replace />;
}
