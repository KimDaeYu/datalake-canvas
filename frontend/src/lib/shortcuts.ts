export type ShortcutAction = "save" | "run";

export interface ShortcutKeyEvent {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
}

/**
 * Maps a keyboard event to a canvas shortcut.
 * Ctrl (Windows/Linux) or Cmd (macOS) + S -> save, + Enter -> run.
 * Alt/Shift combos are ignored so we never swallow other shortcuts or AltGr input.
 */
export function getShortcutAction(event: ShortcutKeyEvent): ShortcutAction | null {
  if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) {
    return null;
  }
  const key = event.key.toLowerCase();
  if (key === "s") return "save";
  if (key === "enter") return "run";
  return null;
}
