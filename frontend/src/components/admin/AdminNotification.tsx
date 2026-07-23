import { useEffect } from 'react';
import { CheckCircle, XCircle, X } from 'lucide-react';

export interface AdminNotificationProps {
  message: string;
  type: 'success' | 'error';
  onClose: () => void;
  visible: boolean;
}

export function AdminNotification({ message, type, onClose, visible }: AdminNotificationProps) {
  useEffect(() => {
    if (!visible) return;
    const timer = setTimeout(() => {
      onClose();
    }, 5000);
    return () => clearTimeout(timer);
  }, [visible, onClose]);

  if (!visible) return null;

  const styles = {
    success: {
      container: 'border-green-200 bg-green-50',
      icon: <CheckCircle className="h-5 w-5 text-green-600" />,
      text: 'text-green-800',
    },
    error: {
      container: 'border-red-200 bg-red-50',
      icon: <XCircle className="h-5 w-5 text-red-600" />,
      text: 'text-red-800',
    },
  };

  const style = styles[type];

  return (
    <div
      className={`fixed top-4 right-4 z-50 flex items-center gap-3 rounded-xl border px-4 py-3 shadow-lg transition-all duration-300 ${style.container}`}
      style={{
        animation: 'slideInRight 0.3s ease-out',
      }}
      role="alert"
    >
      {style.icon}
      <span className={`text-sm font-medium ${style.text}`}>{message}</span>
      <button
        onClick={onClose}
        className="ml-2 flex h-6 w-6 items-center justify-center rounded-full hover:bg-black/5 transition-colors"
        aria-label="Dismiss notification"
      >
        <X className="h-4 w-4 text-[#102247]/60" />
      </button>
    </div>
  );
}
