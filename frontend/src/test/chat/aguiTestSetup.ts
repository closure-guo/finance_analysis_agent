// add-assistant-ui-thread：AG-UI/assistant-ui 全局测试 polyfill。
// jsdom 缺少 ResizeObserver / Element.scrollTo / scrollIntoView，assistant-ui 的
// Viewport（经 App 挂载的 QuickThread）依赖三者；作为 vitest setupFile 在所有
// 测试前统一补齐。（不改动既有 src/test/setup.ts 与任何既有测试文件——深度模式
// 测试零修改约束；本文件同时导出 installJsdomPolyfills 供单独调用。）

export function installJsdomPolyfills(): void {
  const g = globalThis as unknown as Record<string, unknown>
  if (!g.ResizeObserver) {
    g.ResizeObserver = class ResizeObserverStub {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    }
  }
  if (typeof g.scrollTo !== 'function') {
    g.scrollTo = () => {}
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {}
  }
  // assistant-ui Viewport 自动滚底调用 element.scrollTo（jsdom 未实现）
  if (!Element.prototype.scrollTo) {
    Element.prototype.scrollTo = () => {}
  }
}

installJsdomPolyfills()
