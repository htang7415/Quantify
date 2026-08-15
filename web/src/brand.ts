export const PRODUCT_NAME = "Libration";

/**
 * Presents immutable pre-rename catalog prose under the current public brand.
 * The underlying released string and its manifest binding remain unchanged.
 */
export function publicBrandText(value: string): string {
  return value.replaceAll("Quantify", PRODUCT_NAME);
}
