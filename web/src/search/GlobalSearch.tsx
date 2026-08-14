import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { sentenceCase } from "../format";
import { searchReleasedEntities } from "./entityGraph";

export function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const results = useMemo(() => searchReleasedEntities(query), [query]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const editing = target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.tagName === "SELECT" || target?.isContentEditable;
      if (event.key === "/" && !editing) {
        event.preventDefault();
        setOpen(true);
      }
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return <>
    <button aria-label="Search" className="global-search-trigger" type="button" onClick={() => setOpen(true)} aria-haspopup="dialog">
      <span aria-hidden="true">⌕</span><b>Search</b><kbd>/</kbd>
    </button>
    {open && createPortal(<div className="global-search-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) setOpen(false); }}>
      <section className="global-search-dialog" role="dialog" aria-modal="true" aria-labelledby="global-search-title">
        <header>
          <div><p className="terminal-eyebrow">Released data only</p><h2 id="global-search-title">Search Quantify</h2></div>
          <button type="button" onClick={() => setOpen(false)} aria-label="Close search">Close</button>
        </header>
        <label className="global-search-input">
          <span aria-hidden="true">⌕</span>
          <input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Company, ticker, manager, venture firm, ETF, rate, or policy" />
          <kbd>Esc</kbd>
        </label>
        <div className="global-search-summary"><span>{query ? `${results.length} matches` : "Explore released entities"}</span><span>Exact identifiers · deterministic text match</span></div>
        <div className="global-search-results" aria-live="polite">
          {results.map((entity) => <a href={entity.href} key={entity.id}>
            <span className="search-kind">{entity.kind}</span>
            <strong>{entity.symbol && <b>{entity.symbol}</b>}{entity.label}<small>{entity.description}</small></strong>
            <span className="search-release">{entity.availability === "source_review" ? "Source review" : `${entity.sources.length} ${entity.sources.length === 1 ? "release" : "releases"}`}<small>{sentenceCase(entity.sources[0].freshness)}</small></span>
          </a>)}
          {results.length === 0 && <div className="global-search-empty"><strong>No released match.</strong><p>Try an exact ticker, manager, venture firm, ETF, macro series, Treasury maturity, or policy authority.</p></div>}
        </div>
        <footer>Search does not use narrative similarity and cannot create an entity relationship.</footer>
      </section>
    </div>, document.body)}
  </>;
}
