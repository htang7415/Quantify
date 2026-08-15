import { BrandMark } from "./BrandMark";

export function CommercialFooter() {
  return (
    <footer className="commercial-footer">
      <div className="commercial-footer-main page-shell">
        <div className="commercial-footer-brand">
          <a className="site-brand" href="/" aria-label="Libration footer home">
            <BrandMark />
            <span>Libration</span>
          </a>
          <p>See more of what matters. Released information, connected intelligence, and evidence-bound verification for public-company research.</p>
        </div>
        <nav aria-label="Product links">
          <strong>Product</strong>
          <a href="/agent">Verify a claim</a>
          <a href="/product">How it works</a>
          <a href="/coverage">Coverage</a>
        </nav>
        <nav aria-label="Research links">
          <strong>Research</strong>
          <a href="/markets">Markets</a>
          <a href="/investors">Investors</a>
          <a href="/companies">Companies</a>
          <a href="/intelligence">Intelligence</a>
        </nav>
        <nav aria-label="Trust links">
          <strong>Trust</strong>
          <a href="/methodology">Methodology</a>
          <a href="/intelligence/releases">Release operations</a>
          <a href="/methodology#boundaries">Research boundaries</a>
        </nav>
      </div>
      <div className="commercial-footer-legal page-shell">
        <p>Research data and verification only. No price predictions, trade recommendations, brokerage, or personalized investment advice.</p>
        <span>© 2026 Libration</span>
      </div>
    </footer>
  );
}
