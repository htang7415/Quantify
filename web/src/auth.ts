const TOKEN_KEY = "quantify_access_token";
const PKCE_VERIFIER_KEY = "quantify_pkce_verifier";
const PKCE_STATE_KEY = "quantify_pkce_state";

type AuthConfig = {
  clientId: string;
  domain: string;
  redirectUri: string;
  verifyScope: string;
};

function configuration(): AuthConfig {
  const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID;
  const domain = import.meta.env.VITE_COGNITO_DOMAIN;
  const redirectUri = import.meta.env.VITE_COGNITO_REDIRECT_URI;
  const verifyScope = import.meta.env.VITE_COGNITO_VERIFY_SCOPE;
  if (!clientId || !domain || !redirectUri || !verifyScope) {
    throw new Error("Sign-in is not configured in this preview.");
  }
  return { clientId, domain: domain.replace(/\/$/, ""), redirectUri, verifyScope };
}

function base64Url(bytes: Uint8Array): string {
  let text = "";
  bytes.forEach((byte) => {
    text += String.fromCharCode(byte);
  });
  return btoa(text).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function randomValue(): string {
  return base64Url(crypto.getRandomValues(new Uint8Array(32)));
}

async function codeChallenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64Url(new Uint8Array(digest));
}

export function accessToken(): string | null {
  return window.sessionStorage.getItem(TOKEN_KEY);
}

function accessTokenHasScope(token: string, requiredScope: string): boolean {
  const payload = token.split(".")[1];
  if (!payload) return false;
  try {
    const normalized = payload.replaceAll("-", "+").replaceAll("_", "/");
    const json = atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "="));
    const decoded: unknown = JSON.parse(json);
    const scope = typeof (decoded as { scope?: unknown }).scope === "string"
      ? (decoded as { scope: string }).scope
      : "";
    return scope.split(" ").includes(requiredScope);
  } catch {
    return false;
  }
}

export function verifyScopeGranted(): boolean {
  try {
    const token = accessToken();
    return Boolean(token && accessTokenHasScope(token, configuration().verifyScope));
  } catch {
    return false;
  }
}

export async function beginSignIn(): Promise<never> {
  const config = configuration();
  const verifier = randomValue();
  const state = randomValue();
  window.sessionStorage.setItem(PKCE_VERIFIER_KEY, verifier);
  window.sessionStorage.setItem(PKCE_STATE_KEY, state);
  const authorize = new URL(`${config.domain}/oauth2/authorize`);
  authorize.search = new URLSearchParams({
    client_id: config.clientId,
    code_challenge: await codeChallenge(verifier),
    code_challenge_method: "S256",
    redirect_uri: config.redirectUri,
    response_type: "code",
    scope: `openid ${config.verifyScope}`,
    state
  }).toString();
  window.location.assign(authorize);
  return new Promise<never>(() => undefined);
}

export async function finishSignIn(): Promise<boolean> {
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code");
  if (!code) return false;
  const config = configuration();
  const expectedState = window.sessionStorage.getItem(PKCE_STATE_KEY);
  const verifier = window.sessionStorage.getItem(PKCE_VERIFIER_KEY);
  if (!expectedState || !verifier || params.get("state") !== expectedState) {
    throw new Error("Sign-in response could not be verified. Please try again.");
  }
  const response = await fetch(`${config.domain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: config.clientId,
      code,
      code_verifier: verifier,
      grant_type: "authorization_code",
      redirect_uri: config.redirectUri
    })
  });
  if (!response.ok) throw new Error("Sign-in could not be completed. Please try again.");
  const payload: unknown = await response.json();
  if (!payload || typeof payload !== "object" || typeof (payload as { access_token?: unknown }).access_token !== "string") {
    throw new Error("Sign-in did not return a valid access token.");
  }
  const token = (payload as { access_token: string }).access_token;
  if (!accessTokenHasScope(token, config.verifyScope)) {
    throw new Error("Sign-in did not grant the Libration verify permission.");
  }
  window.sessionStorage.setItem(TOKEN_KEY, token);
  window.sessionStorage.removeItem(PKCE_VERIFIER_KEY);
  window.sessionStorage.removeItem(PKCE_STATE_KEY);
  window.history.replaceState({}, document.title, window.location.pathname);
  return true;
}
