import { SiteNav } from "./SiteNav";

export function NotFoundPage() {
  return <main className="data-app"><SiteNav active="overview" action={{ label: "Verify a claim", href: "/agent" }} /><section className="source-review-page"><p className="terminal-eyebrow">404 / Page not found</p><h1>This route is outside the released product.</h1><p>Return to the current Libration overview.</p><a className="source-button" href="/">Open overview</a></section></main>;
}
