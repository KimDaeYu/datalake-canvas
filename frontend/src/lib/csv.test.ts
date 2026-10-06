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
    const rows = [["Hello, World", 'He said "Hi"'] , ["Line 1\nLine 2", null]];
    const csv = toCsv(columns, rows);
    expect(csv).toBe(
      'title,description\n"Hello, World","He said ""Hi"""\n"Line 1\nLine 2",'
    );
  });

  it("handles empty rows and columns gracefully", () => {
    expect(toCsv([], [])).toBe("");
    expect(toCsv(["col1"], [])).toBe("col1");
  });
});
