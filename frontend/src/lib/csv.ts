/**
 * Pure helper that converts columns and rows into a CSV string.
 * Cells are quoted RFC 4180 style (commas, quotes and line breaks; quotes are doubled), null and
 * undefined become empty cells. Rows are separated by "\n" rather than the RFC's "\r\n".
 */
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
