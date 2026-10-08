import { describe, expect, it } from "vitest";
import { toCsv } from "./csv";

describe("toCsv", () => {
  it("converts simple columns and rows to CSV", () => {
    const columns = ["id", "name", "active"];
    const rows = [
      [1, "Alice", true],
      [2, "Bob", false],
    ];
    const csv = toCsv(columns, rows);
    expect(csv).toBe("id,name,active\n1,Alice,true\n2,Bob,false");
  });

  it("escapes cells containing commas, quotes, and newlines", () => {
    const columns = ["title", "description"];
    const rows = [
      ["Hello, World", 'He said "Hi"'],
      ["Line 1\nLine 2", null],
    ];
    const csv = toCsv(columns, rows);
    expect(csv).toBe('title,description\n"Hello, World","He said ""Hi"""\n"Line 1\nLine 2",');
  });

  it("quotes cells containing a carriage return", () => {
    expect(toCsv(["a"], [["x\ry"]])).toBe('a\n"x\ry"');
  });

  it("keeps falsy values: 0, false and the empty string are not turned into null", () => {
    expect(toCsv(["n", "b", "s", "z"], [[0, false, "", null]])).toBe("n,b,s,z\n0,false,,");
  });

  it("handles empty rows and columns gracefully", () => {
    expect(toCsv([], [])).toBe("");
    expect(toCsv(["col1"], [])).toBe("col1");
  });
});
