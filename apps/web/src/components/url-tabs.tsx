'use client';

import { useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';

const EMPTY_HASHES: Readonly<Record<string, never>> = Object.freeze({});

export function useUrlTab<const T extends string>(
  key: string,
  initial: T,
  values: readonly T[],
  hashes: Readonly<Record<string, T>> = EMPTY_HASHES,
): readonly [T, (next: T) => void] {
  const [active, setActive] = useState<T>(initial);
  const search = useSearchParams().toString();

  useEffect(() => {
    const sync = () => {
      const url = new URL(window.location.href);
      const candidate = url.searchParams.get(key);
      const hashValue = hashes[url.hash];
      setActive(values.includes(candidate as T) ? candidate as T : hashValue && values.includes(hashValue) ? hashValue : initial);
    };
    sync();
    window.addEventListener('popstate', sync);
    window.addEventListener('hashchange', sync);
    return () => {
      window.removeEventListener('popstate', sync);
      window.removeEventListener('hashchange', sync);
    };
  }, [hashes, initial, key, values, search]);

  const select = useCallback((next: T) => {
    if (!values.includes(next)) return;
    const url = new URL(window.location.href);
    url.searchParams.set(key, next);
    url.hash = '';
    window.history.pushState(window.history.state, '', url);
    setActive(next);
  }, [key, values]);

  return [active, select] as const;
}

export function UrlTabs<const T extends string>({
  label,
  values,
  labels,
  active,
  onChange,
  idPrefix,
}: {
  label: string;
  values: readonly T[];
  labels: Readonly<Record<T, string>>;
  active: T;
  onChange: (next: T) => void;
  idPrefix: string;
}) {
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);

  const handleKeyDown = useCallback((event: KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const focusedIndex = buttons.current.findIndex((button) => button === document.activeElement);
    const activeIndex = focusedIndex >= 0 ? focusedIndex : values.indexOf(active);
    const nextIndex = event.key === 'Home' ? 0
      : event.key === 'End' ? values.length - 1
      : (activeIndex + (event.key === 'ArrowRight' ? 1 : values.length - 1)) % values.length;
    const next = values[nextIndex];
    if (!next) return;
    onChange(next);
    buttons.current[nextIndex]?.focus();
  }, [active, onChange, values]);

  return (
    <div className="route-tablist" role="tablist" aria-label={label} onKeyDown={handleKeyDown}>
      {values.map((value, index) => (
        <button
          key={value}
          ref={(node) => { buttons.current[index] = node; }}
          type="button"
          role="tab"
          id={`${idPrefix}-tab-${value}`}
          aria-controls={`${idPrefix}-panel`}
          aria-selected={active === value}
          tabIndex={active === value ? 0 : -1}
          onClick={() => onChange(value)}
        >
          {labels[value]}
        </button>
      ))}
    </div>
  );
}
