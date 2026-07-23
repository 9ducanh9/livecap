import { Search } from 'lucide-react';

export interface FilterBarProps {
  searchValue: string;
  onSearchChange: (value: string) => void;
  tierFilter: string;
  onTierChange: (tier: string) => void;
  statusFilter: string;
  onStatusChange: (status: string) => void;
}

export function FilterBar({
  searchValue,
  onSearchChange,
  tierFilter,
  onTierChange,
  statusFilter,
  onStatusChange,
}: FilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Email search input */}
      <div className="relative flex-1 min-w-[200px]">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#102247]/40" />
        <input
          type="text"
          value={searchValue}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search by email..."
          className="w-full rounded-lg border border-[#dce5f2] bg-white py-2 pl-9 pr-3 text-sm text-[#102247] placeholder:text-[#102247]/40 focus:border-[#0a9c88] focus:outline-none focus:ring-1 focus:ring-[#0a9c88]"
        />
      </div>

      {/* Tier dropdown */}
      <select
        value={tierFilter}
        onChange={(e) => onTierChange(e.target.value)}
        className="rounded-lg border border-[#dce5f2] bg-white px-3 py-2 text-sm text-[#102247] focus:border-[#0a9c88] focus:outline-none focus:ring-1 focus:ring-[#0a9c88]"
        aria-label="Filter by tier"
      >
        <option value="">All Tiers</option>
        <option value="free">Free</option>
        <option value="pro">Pro</option>
        <option value="business">Business</option>
      </select>

      {/* Status dropdown */}
      <select
        value={statusFilter}
        onChange={(e) => onStatusChange(e.target.value)}
        className="rounded-lg border border-[#dce5f2] bg-white px-3 py-2 text-sm text-[#102247] focus:border-[#0a9c88] focus:outline-none focus:ring-1 focus:ring-[#0a9c88]"
        aria-label="Filter by status"
      >
        <option value="">All Statuses</option>
        <option value="enabled">Enabled</option>
        <option value="disabled">Disabled</option>
      </select>
    </div>
  );
}
