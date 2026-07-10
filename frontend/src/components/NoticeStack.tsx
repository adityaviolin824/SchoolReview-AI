type NoticeStackProps = {
  message: string;
  error: string;
};

export function NoticeStack({ message, error }: NoticeStackProps) {
  if (!message && !error) {
    return null;
  }

  return (
    <section className="notice-stack" aria-live="polite">
      {message && <div className="notice">{message}</div>}
      {error && <div className="notice notice-error">{error}</div>}
    </section>
  );
}
