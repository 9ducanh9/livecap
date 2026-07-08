import React from 'react';

interface GlassPanelProps {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
}

export const GlassPanel: React.FC<GlassPanelProps> = ({ children, className = '', onClick }) => {
  return (
    <div
      onClick={onClick}
      className={`relative overflow-hidden border border-white/10 bg-white/[0.03] backdrop-blur-pro ${className}`}
    >
      {/* Subtle inner highlight */}
      <div className="absolute inset-0 pointer-events-none border border-white/5" />
      {children}
    </div>
  );
};
