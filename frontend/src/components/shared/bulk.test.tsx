import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useSelection } from './bulk';

describe('useSelection', () => {
  const ids = ['a', 'b', 'c'];

  it('toggles single rows and tracks the partial state', () => {
    const { result } = renderHook(() => useSelection(ids, 'page1'));
    act(() => result.current.toggle('a'));
    expect(result.current.selected).toEqual(['a']);
    expect(result.current.someSelected).toBe(true);
    expect(result.current.allSelected).toBe(false);
    act(() => result.current.toggle('a'));
    expect(result.current.selected).toEqual([]);
  });

  it('selects and clears every row on the page', () => {
    const { result } = renderHook(() => useSelection(ids, 'page1'));
    act(() => result.current.toggleAll());
    expect(result.current.allSelected).toBe(true);
    act(() => result.current.toggleAll());
    expect(result.current.selected).toEqual([]);
  });

  it('forgets the selection when the page or filters change', () => {
    const { result, rerender } = renderHook(
      ({ key }) => useSelection(ids, key),
      { initialProps: { key: 'page1' } },
    );
    act(() => result.current.toggle('b'));
    rerender({ key: 'page2' });
    expect(result.current.selected).toEqual([]);
  });
});
