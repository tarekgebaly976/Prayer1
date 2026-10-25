import next from "eslint-config-next";

export default [
  ...next,
  { ignores: [".next/**", "node_modules/**", "public/sw.js", "playwright-report/**", "test-results/**"] },
];
