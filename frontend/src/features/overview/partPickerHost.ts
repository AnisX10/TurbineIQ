const listeners = new Set<() => void>()
let host: HTMLElement | null = null

export function setPartPickerHost(element: HTMLElement | null): void {
  if (host === element) return
  host = element
  listeners.forEach((listener) => listener())
}

export function getPartPickerHost(): HTMLElement | null {
  return host
}

export function subscribePartPickerHost(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
