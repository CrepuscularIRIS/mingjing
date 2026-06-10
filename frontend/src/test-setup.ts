import '@testing-library/jest-dom';

// jsdom lacks these browser APIs that ReactFlow (and scrollIntoView in the
// EvidenceDrawer) rely on. Provide minimal no-op polyfills so components that
// use them render in tests without throwing.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
if (!('ResizeObserver' in globalThis)) {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver =
    ResizeObserverStub;
}

// jsdom lacks IntersectionObserver, which `motion`'s useInView (used by the
// Magic UI BlurFade arrival animation) instantiates. A no-op stub keeps those
// components rendering in tests; arrival animations are not asserted on.
class IntersectionObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): [] {
    return [];
  }
}
if (!('IntersectionObserver' in globalThis)) {
  (globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver =
    IntersectionObserverStub;
}

if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = (): void => {};
}

// ReactFlow measures the DOM via getBoundingClientRect; jsdom returns zeros,
// which is fine — node content still renders into the DOM for assertions.
