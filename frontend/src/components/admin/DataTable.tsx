import type { ReactNode } from 'react';
import { ChevronLeft, ChevronRight, LoaderCircle } from 'lucide-react';

export interface Column<T> {
  key: string;
  header: string;
  render?: (item: T) => ReactNode;
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  page: number;
  totalPages: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  loading?: boolean;
}

export function DataTable<T extends Record<string, unknown>>({
  columns,
  data,
  page,
  totalPages,
  pageSize,
  onPageChange,
  onPageSizeChange,
  loading = false,
}: DataTableProps<T>) {
  const pageSizeOptions = [10, 20, 50];

  // Generate visible page numbers
  const getPageNumbers = (): (number | 'ellipsis')[] => {
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, i) => i + 1);
    }
    const pages: (number | 'ellipsis')[] = [1];
    if (page > 3) pages.push('ellipsis');
    const start = Math.max(2, page - 1);
    const end = Math.min(totalPages - 1, page + 1);
    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    if (page < totalPages - 2) pages.push('ellipsis');
    if (totalPages > 1) pages.push(totalPages);
    return pages;
  };

  if (loading) {
    return (
      <div className="rounded-2xl border border-[#dce5f2] bg-white shadow-sm overflow-hidden">
        <div className="flex items-center justify-center py-16">
          <LoaderCircle className="h-6 w-6 animate-spin text-[#0a9c88]" />
          <span className="ml-2 text-sm text-[#102247]/60">Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-[#dce5f2] bg-white shadow-sm overflow-hidden">
      {/* Table with horizontal scroll */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#dce5f2] bg-[#f7f8fc]">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#102247]/60"
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-12 text-center text-sm text-[#102247]/50"
                >
                  No data available
                </td>
              </tr>
            ) : (
              data.map((item, rowIdx) => (
                <tr
                  key={rowIdx}
                  className="border-b border-[#dce5f2] last:border-b-0 hover:bg-[#f7f8fc]/50 transition-colors"
                >
                  {columns.map((col) => (
                    <td key={col.key} className="px-4 py-3 text-[#102247]">
                      {col.render
                        ? col.render(item)
                        : String(item[col.key] ?? '')}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#dce5f2] px-4 py-3">
        {/* Page size selector */}
        <div className="flex items-center gap-2">
          <label htmlFor="page-size" className="text-xs text-[#102247]/60">
            Rows per page:
          </label>
          <select
            id="page-size"
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="rounded-md border border-[#dce5f2] bg-white px-2 py-1 text-xs text-[#102247] focus:border-[#0a9c88] focus:outline-none focus:ring-1 focus:ring-[#0a9c88]"
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </div>

        {/* Page navigation */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="flex h-8 w-8 items-center justify-center rounded-md border border-[#dce5f2] text-[#102247] transition-colors hover:bg-[#f7f8fc] disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>

          {getPageNumbers().map((p, idx) =>
            p === 'ellipsis' ? (
              <span key={`ellipsis-${idx}`} className="px-1 text-xs text-[#102247]/40">
                …
              </span>
            ) : (
              <button
                key={p}
                onClick={() => onPageChange(p)}
                className={`flex h-8 w-8 items-center justify-center rounded-md text-xs font-medium transition-colors ${
                  p === page
                    ? 'bg-[#0a9c88] text-white'
                    : 'border border-[#dce5f2] text-[#102247] hover:bg-[#f7f8fc]'
                }`}
              >
                {p}
              </button>
            )
          )}

          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
            className="flex h-8 w-8 items-center justify-center rounded-md border border-[#dce5f2] text-[#102247] transition-colors hover:bg-[#f7f8fc] disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
