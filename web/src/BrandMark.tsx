/**
 * A compact lunar-libration mark.
 *
 * The disc is the Moon. The opposed arcs and endpoint dots show the apparent
 * change in viewing angle that reveals more of the lunar surface over time.
 */
export function BrandMark() {
  return (
    <svg
      aria-hidden="true"
      className="site-brand-mark"
      focusable="false"
      viewBox="0 0 32 32"
    >
      <circle className="libration-disc" cx="16" cy="16" r="7.1" />
      <path className="libration-meridian" d="M15.8 9.1c-3 2.2-3 11.6 0 13.8" />
      <path className="libration-arc" d="M7.1 11.7c3.1-4.3 14.7-5.5 18.1.7" />
      <path className="libration-arc" d="M24.9 20.3c-3.1 4.3-14.7 5.5-18.1-.7" />
      <circle className="libration-point" cx="7.1" cy="11.7" r="1.15" />
      <circle className="libration-point" cx="24.9" cy="20.3" r="1.15" />
    </svg>
  );
}
