# web

CommerceAgent 的 **Web 前端**（React + TypeScript + Vite）。当前主要承载本地流转验证页 **Flow Playground**（`src/features/validation/`）；真实产品 UI 由后续业务任务实现。

**进度与"下一步做什么"只读** [`PROJECT_PROGRESS.md`](../PROJECT_PROGRESS.md)。

本机注意：前端命令一律用 `npm.cmd`（PowerShell 执行策略会拦 `npm.ps1`）；dev server 只监听 IPv6，页面用 `http://localhost:5173/`（不是 `127.0.0.1`）。

---

以下是 Vite 官方模板自带的说明，保留作参考：

# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.
