import React from 'react';

interface ProButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg' | 'xl';
  loading?: boolean;
}

export const ProButton: React.FC<ProButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  className = '',
  disabled,
  ...props
}) => {
  const baseStyles = 'relative inline-flex items-center justify-center font-mono text-xs uppercase tracking-wider transition-all duration-200 disabled:cursor-not-allowed overflow-hidden active:scale-95 select-none';

  const variants = {
    primary: 'bg-crimson text-white hover:bg-crimson/90 shadow-[0_0_20px_rgba(225,29,72,0.2)] disabled:bg-white/5 disabled:text-white/20 disabled:border disabled:border-white/10 disabled:shadow-none',
    secondary: 'bg-emerald-pro text-white hover:bg-emerald-pro/90 shadow-[0_0_20px_rgba(5,150,105,0.2)] disabled:bg-white/5 disabled:text-white/20 disabled:border disabled:border-white/10 disabled:shadow-none',
    outline: 'border border-white/20 text-white hover:bg-white/5 backdrop-blur-sm disabled:border-white/5 disabled:text-white/15',
    ghost: 'text-white/60 hover:text-white hover:bg-white/5 disabled:text-white/10',
    danger: 'bg-rose-600 text-white hover:bg-rose-700 shadow-[0_0_20px_rgba(225,29,72,0.2)] disabled:bg-white/5 disabled:text-white/20 disabled:shadow-none',
  };

  const sizes = {
    sm: 'px-3 py-1.5 text-[10px]',
    md: 'px-6 py-3',
    lg: 'px-8 py-4 text-sm font-bold',
    xl: 'px-10 py-5 text-base font-bold',
  };

  return (
    <button
      className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <span className="flex items-center gap-2">
          <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <span className="animate-pulse">Loading</span>
        </span>
      ) : (
        children
      )}

      {/* Hover effect highlight */}
      {!disabled && !loading && (
        <div className="absolute inset-0 pointer-events-none bg-gradient-to-tr from-white/10 to-transparent opacity-0 transition-opacity hover:opacity-100" />
      )}
    </button>
  );
};
