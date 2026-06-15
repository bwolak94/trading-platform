import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  // Ignore build artifacts and generated files
  {
    ignores: [
      "dist/**",
      "coverage/**",
      "node_modules/**",
      "src/types/api.generated.ts",
      "postcss.config.js",
      "tailwind.config.js",
      "eslint.config.js",
      "public/**",
      "**/*.js",
      "vite.config.ts",
      "vitest.config.ts",
    ],
  },

  // Base JS recommended
  js.configs.recommended,

  // TypeScript recommended with type-checking (strict is too noisy for this codebase)
  ...tseslint.configs.recommendedTypeChecked,

  // React Hooks rules
  {
    plugins: {
      "react-hooks": reactHooks,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
    },
  },

  // Main config for all TS/TSX files
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2024,
      globals: {
        ...globals.browser,
        ...globals.es2024,
      },
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // ── TypeScript — real safety rules (keep as errors) ────────────────
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { prefer: "type-imports", fixStyle: "inline-type-imports" },
      ],
      "@typescript-eslint/no-import-type-side-effects": "error",
      // Downgraded: real issues but too pervasive to fix atomically — track as warnings
      "@typescript-eslint/no-floating-promises": "warn",
      "@typescript-eslint/no-misused-promises": "warn",
      "@typescript-eslint/await-thenable": "error",

      // ── TypeScript — downgraded to warn (noisy in large codebases) ─────
      "@typescript-eslint/no-unsafe-assignment": "warn",
      "@typescript-eslint/no-unsafe-member-access": "warn",
      "@typescript-eslint/no-unsafe-call": "warn",
      "@typescript-eslint/no-unsafe-return": "warn",
      "@typescript-eslint/no-unsafe-argument": "warn",
      "@typescript-eslint/no-non-null-assertion": "warn",
      // Objects without toString() in template literals — too many false positives
      // with union types and React children
      "@typescript-eslint/no-base-to-string": "warn",
      // Promise.reject() without Error — common legacy pattern
      "@typescript-eslint/prefer-promise-reject-errors": "warn",
      // Unused expressions — sometimes used as type assertions or side effects
      "@typescript-eslint/no-unused-expressions": "warn",
      "react-hooks/exhaustive-deps": "warn",

      // ── TypeScript — disabled (too strict / false positives) ───────────
      // Numbers in template literals are a common, safe pattern
      "@typescript-eslint/restrict-template-expressions": "off",
      // `?? fallback` patterns can be intentional defensive code
      "@typescript-eslint/no-unnecessary-condition": "off",
      // `() => setState(x)` is idiomatic React
      "@typescript-eslint/no-confusing-void-expression": "off",
      // Empty catch blocks / functions are sometimes needed
      "@typescript-eslint/no-empty-function": "off",
      // Allow `require-await` flexibility in async lifecycle hooks
      "@typescript-eslint/require-await": "off",
      // Inferrable types are fine as explicit documentation
      "@typescript-eslint/no-inferrable-types": "off",
      // Prefer optional chain — already handled by TypeScript itself
      "@typescript-eslint/prefer-optional-chain": "warn",
      "@typescript-eslint/prefer-nullish-coalescing": "warn",

      // ── React Hooks ────────────────────────────────────────────────────
      "react-hooks/rules-of-hooks": "error",

      // ── General best practices ─────────────────────────────────────────
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "prefer-const": "error",
      "no-var": "error",
      eqeqeq: ["error", "always", { null: "ignore" }],

      // ── Import hygiene ─────────────────────────────────────────────────
      // Disable built-in rule: it conflicts with consistent-type-imports when
      // value and type imports from the same module live in separate statements.
      // TypeScript already prevents actual duplicate runtime imports.
      "no-duplicate-imports": "off",
    },
  },

  // Relax some rules in test files
  {
    files: ["**/__tests__/**/*.{ts,tsx}", "**/*.test.{ts,tsx}", "**/*.spec.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-unsafe-assignment": "off",
      "@typescript-eslint/no-unsafe-member-access": "off",
      "@typescript-eslint/no-unsafe-call": "off",
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-non-null-assertion": "off",
    },
  },
);
