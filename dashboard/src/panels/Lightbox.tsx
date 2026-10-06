// A picture shown large over the dashboard, in a native <dialog>: Esc, the × and a click outside the picture all
// close it, focus goes back to what opened it, and the page behind cannot be clicked meanwhile.
//
// The dialog is always mounted and `open` drives it. Opening it from an effect on mount broke under StrictMode, which
// mounts, cleans up and mounts again: the clean-up's close() fired the dialog's "close" event, which told the parent
// to hide it, so it flashed open and shut. Syncing a flag is the same however many times it runs.
import { useEffect, useRef } from "react";

type Props = { open: boolean; src: string; alt: string; caption?: string; onClose: () => void };

export default function Lightbox({ open, src, alt, caption, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = dialog.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    else if (!open && d.open) d.close(); // puts the focus back on what opened it
  }, [open]);

  return (
    <dialog
      ref={dialog}
      className="lightbox"
      aria-label={alt}
      onClose={onClose} // fires after Esc or close(); the parent already knows when it was the flag that closed it
      // The backdrop belongs to the dialog itself, so a click whose target is the dialog is a click outside the picture.
      onClick={(e) => {
        if (e.target === dialog.current) onClose();
      }}
      // Esc closes the picture, not the Tickets panel behind it (App's Esc handler listens on the document).
      onKeyDown={(e) => {
        if (e.key === "Escape") e.stopPropagation();
      }}
    >
      {open && (
        <>
          <figure>
            <img src={src} alt={alt} />
            {caption && <figcaption>{caption}</figcaption>}
          </figure>
          <button className="lightbox-close" aria-label="Close picture" onClick={onClose}>
            <svg viewBox="0 0 20 20" aria-hidden="true">
              <path d="m5.5 5.5 9 9m0-9-9 9" />
            </svg>
          </button>
        </>
      )}
    </dialog>
  );
}
