import { useEffect, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";

type Props = {
  src: string;
  alt?: string;
  className?: string;
  /** Extra classes for the full-size image in the lightbox */
  fullClassName?: string;
};

/**
 * Thumbnail that opens a full-viewport lightbox on click.
 */
export function ZoomableImage({ src, alt = "", className = "", fullClassName = "" }: Props) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const onThumbKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setOpen(true);
    }
  };

  return (
    <>
      <button
        type="button"
        className="p-0 m-0 border-0 bg-transparent cursor-zoom-in rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
        onClick={() => setOpen(true)}
        onKeyDown={onThumbKey}
        title="Nhấp để xem ảnh đầy đủ"
        aria-label="Phóng to ảnh"
      >
        <img src={src} alt={alt} className={className} loading="lazy" />
      </button>
      {open &&
        createPortal(
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Ảnh đầy đủ"
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/85 p-3 sm:p-6"
            onClick={() => setOpen(false)}
          >
            <button
              type="button"
              className="absolute top-3 right-3 z-[101] rounded-lg border border-white/20 bg-black/50 px-3 py-1.5 text-sm text-white hover:bg-black/70"
              onClick={() => setOpen(false)}
              aria-label="Đóng"
            >
              Đóng
            </button>
            <img
              src={src}
              alt={alt}
              className={`max-h-[min(92vh,1200px)] max-w-[min(96vw,1400px)] object-contain rounded-lg shadow-2xl cursor-default ${fullClassName}`}
              onClick={(e) => e.stopPropagation()}
            />
          </div>,
          document.body,
        )}
    </>
  );
}
