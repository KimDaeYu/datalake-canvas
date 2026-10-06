/** Pure helper to convert columns and rows into RFC 4180 compliant CSV string. */
export function toCsv(columns: string[], rows: unknown[][]): string {
  const escapeCell = (cell: unknown): string => {
    if (cell === null || cell === undefined) {
      return "";
    }
    const str = String(cell);
    if (str.includes(",") || str.includes('"') || str.includes("\n") || str.includes("\r")) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };

  const headerRow = columns.map(escapeCell).join(",");
  const dataRows = rows.map((row) => row.map(escapeCell).join(","));

  return [headerRow, ...dataRows].join("\n");
}
