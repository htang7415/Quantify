export type SectionConnection = {
  label: string;
  detail: string;
  href: string;
};

export function SectionConnections({ items }: { items: SectionConnection[] }) {
  return (
    <nav className="section-connections page-shell" aria-label="Connected research">
      <div className="section-connections-title">
        <span>Connected research</span>
        <strong>Follow exact released relationships.</strong>
      </div>
      <div className="section-connections-links">
        {items.map((item) => (
          <a href={item.href} key={item.href}>
            <span>{item.label}</span>
            <b>{item.detail}</b>
            <i>Open →</i>
          </a>
        ))}
      </div>
    </nav>
  );
}
