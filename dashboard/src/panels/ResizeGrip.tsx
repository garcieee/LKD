import { useEffect, useRef } from "react";

// The drag handle on the left edge of a docked panel (Insights, Forecast). Drag it to resize; past 70% of the window the
// panel snaps to full screen, and dragging back out drops it to the widest free size. The map's stage reads the same
// --insights-w from the shell, so the map follows live.
const MIN_W = 340;
const FULL_AT = 0.7;

export default function ResizeGrip() {
  const grip = useRef<HTMLButtonElement>(null);
  const panel = () => grip.current?.closest<HTMLElement>(".insights") ?? null;
  const shell = () => panel()?.closest<HTMLElement>(".shell");
  useEffect(() => {
    const el = shell(); // captured now: the ref is already null when the cleanup runs
    return () => el?.style.removeProperty("--insights-w");
  }, []);

  // Past FULL_AT the panel snaps to full screen. Just under it is the widest free size.
  function setWidth(w: number, allowFull = true) {
    const full = allowFull && w >= innerWidth * FULL_AT;
    if (full !== panel()?.hasAttribute("data-full")) {
      // Animate only the snap in or out of full screen; a free drag has to track the pointer.
      const el = shell();
      el?.setAttribute("data-anim", "");
      setTimeout(() => el?.removeAttribute("data-anim"), 260);
    }
    const px = full ? innerWidth : Math.min(Math.max(MIN_W, w), innerWidth * FULL_AT - 1);
    shell()?.style.setProperty("--insights-w", `${px}px`);
    panel()?.toggleAttribute("data-full", full);
  }
  // Leaving full screen: the pointer is still in the snap zone, so hold the free size until it leaves.
  const left = useRef(false);
  // Window listeners rather than pointer capture: they keep working when the pointer leaves the button,
  // crosses the map or the sidebar, or the browser starts a text selection.
  const startDrag = (e: React.PointerEvent) => {
    e.preventDefault();
    left.current = false;
    let snapX = 0; // where the pointer was when the panel went full screen
    const move = (ev: PointerEvent) => {
      const wasFull = !!panel()?.hasAttribute("data-full");
      if (wasFull && ev.clientX > snapX + 48) left.current = true; // dragged back out: drop to the free size
      if (ev.clientX > innerWidth * (1 - FULL_AT)) left.current = false;
      setWidth(innerWidth - ev.clientX, !left.current);
      if (!wasFull && panel()?.hasAttribute("data-full")) snapX = ev.clientX;
      // Mapbox listens for window resize and redraws in the same frame, with no flicker.
      dispatchEvent(new Event("resize"));
    };
    const stop = () => {
      removeEventListener("pointermove", move);
      removeEventListener("pointerup", stop);
      removeEventListener("pointercancel", stop);
      document.body.style.userSelect = "";
      shell()?.removeAttribute("data-dragging");
      dispatchEvent(new Event("resize")); // once more, now the map re-frames the city
    };
    document.body.style.userSelect = "none";
    shell()?.setAttribute("data-dragging", ""); // the map follows the size only, see MapCanvas
    addEventListener("pointermove", move);
    addEventListener("pointerup", stop);
    addEventListener("pointercancel", stop);
  };
  const nudge = (e: React.KeyboardEvent) => {
    const w = panel()?.offsetWidth ?? 0;
    if (e.key === "ArrowLeft") setWidth(w + 40);
    else if (e.key === "ArrowRight") setWidth(w - 40, false); // from full screen this steps down to the widest free size
  };

  return (
    <button
      ref={grip}
      type="button"
      className="grip"
      aria-label="Resize panel (drag, or use the left and right arrow keys)"
      onPointerDown={startDrag}
      onKeyDown={nudge}
    >
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <path d="M8 5v10M12 5v10" />
      </svg>
    </button>
  );
}
