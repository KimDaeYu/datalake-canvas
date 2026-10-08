import { describe, expect, it } from "vitest";
import { getShortcutAction, type ShortcutKeyEvent } from "./shortcuts";

const press = (key: string, mods: Partial<ShortcutKeyEvent> = {}): ShortcutKeyEvent => ({
  key,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  shiftKey: false,
  ...mods,
});

describe("getShortcutAction", () => {
  it("maps Ctrl+S and Cmd+S to save", () => {
    expect(getShortcutAction(press("s", { ctrlKey: true }))).toBe("save");
    expect(getShortcutAction(press("s", { metaKey: true }))).toBe("save");
  });

  it("handles an uppercase S (Caps Lock)", () => {
    expect(getShortcutAction(press("S", { ctrlKey: true }))).toBe("save");
  });

  it("maps Ctrl+Enter and Cmd+Enter to run", () => {
    expect(getShortcutAction(press("Enter", { ctrlKey: true }))).toBe("run");
    expect(getShortcutAction(press("Enter", { metaKey: true }))).toBe("run");
  });

  it("ignores keys without Ctrl/Cmd", () => {
    expect(getShortcutAction(press("s"))).toBeNull();
    expect(getShortcutAction(press("Enter"))).toBeNull();
  });

  it("ignores Alt and Shift combinations", () => {
    expect(getShortcutAction(press("s", { ctrlKey: true, altKey: true }))).toBeNull();
    expect(getShortcutAction(press("s", { ctrlKey: true, shiftKey: true }))).toBeNull();
    expect(getShortcutAction(press("Enter", { metaKey: true, shiftKey: true }))).toBeNull();
  });

  it("ignores other Ctrl/Cmd shortcuts", () => {
    expect(getShortcutAction(press("c", { ctrlKey: true }))).toBeNull();
    expect(getShortcutAction(press("z", { metaKey: true }))).toBeNull();
  });
});
