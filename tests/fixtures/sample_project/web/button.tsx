import { api } from "./client";

export function Button() {
  return <button data-base={api.base}>ok</button>;
}

function internalHelper() {
  return 0;
}
