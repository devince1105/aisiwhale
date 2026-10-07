"use client";

// The command palette (AD-03): one box to go anywhere, switch company, or run an action — type to
// narrow, ↑ ↓ to choose, Enter to run, Esc to close. A combobox over a listbox, so a screen
// reader hears the option the arrows reach; Enter while an IME is still choosing does nothing.
import { useId, useMemo, useState, type KeyboardEvent } from "react";

import { pick, type Command } from "./commands";
import { Modal } from "./Dialog";
import { Icon } from "./icons";
import { SHORTCUTS } from "./hotkeys";

export function CommandPalette({ commands, onClose }: { commands: readonly Command[]; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const found = useMemo(() => pick(commands, query), [commands, query]);
  const groups = useMemo(() => {
    const order: Command["group"][] = [];
    for (const c of found) if (!order.includes(c.group)) order.push(c.group);
    return order.map((group) => ({ group, items: found.filter((c) => c.group === group) }));
  }, [found]);
  // the arrows walk the options in the order they are shown
  const shown = groups.flatMap((g) => g.items);
  const listId = useId();
  const optionId = (i: number) => `${listId}-${i}`;
  const at = Math.min(active, Math.max(0, shown.length - 1));

  const run = (command: Command | undefined) => {
    if (!command) return;
    onClose();
    command.run();
  };

  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.nativeEvent.isComposing) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (shown.length === 0) return;
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((at + step + shown.length) % shown.length);
      document.getElementById(optionId((at + step + shown.length) % shown.length))?.scrollIntoView?.({ block: "nearest" });
    } else if (event.key === "Enter") {
      event.preventDefault();
      run(shown[at]);
    }
  };

  let index = -1;
  return (
    <Modal
      onClose={onClose}
      label="指令面板"
      marker="palette"
      className="mx-auto mt-[12vh] mb-auto w-[min(36rem,calc(100vw-2rem))] rounded-xl border border-line p-0 shadow-2xl"
    >
      <div className="flex items-center gap-2 border-b border-line px-4">
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} aria-hidden="true" className="size-4 shrink-0 text-muted">
          <circle cx="9" cy="9" r="5.5" />
          <path d="M13 13l4 4" strokeLinecap="round" />
        </svg>
        <input
          autoFocus
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-activedescendant={shown.length ? optionId(at) : undefined}
          aria-label="搜尋頁面、公司或動作"
          placeholder="搜尋頁面、公司或動作…"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActive(0);
          }}
          onKeyDown={onKey}
          className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted"
        />
        <kbd className="rounded border border-line px-1.5 text-[11px] text-muted">Esc</kbd>
      </div>
      <ul id={listId} role="listbox" aria-label="結果" className="max-h-[50vh] overflow-y-auto p-2">
        {shown.length === 0 ? (
          <li role="presentation" className="px-3 py-6 text-center text-sm text-muted">
            找不到「{query}」
          </li>
        ) : (
          groups.map(({ group, items }) => (
            <li key={group} role="presentation">
              <p className="px-2 pt-2 pb-1 text-[11px] font-semibold tracking-wider text-muted">{group}</p>
              <ul role="group" aria-label={group}>
                {items.map((command) => {
                  index += 1;
                  const i = index;
                  return (
                    <li
                      key={command.id}
                      id={optionId(i)}
                      role="option"
                      aria-selected={i === at}
                      onMouseMove={() => setActive(i)}
                      onClick={() => run(command)}
                      className={`flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm ${i === at ? "bg-accent/10 text-accent" : ""}`}
                    >
                      {command.icon ? <Icon name={command.icon} className="size-4" /> : <span className="size-4" aria-hidden="true" />}
                      <span className="truncate">{command.label}</span>
                      {command.hint && command.hint !== command.group ? (
                        <span className="truncate text-xs text-muted">{command.hint}</span>
                      ) : null}
                      <span className="grow" />
                      {command.keys ? <Keys keys={command.keys} /> : null}
                    </li>
                  );
                })}
              </ul>
            </li>
          ))
        )}
      </ul>
    </Modal>
  );
}

function Keys({ keys }: { keys: string }) {
  return (
    <span className="flex gap-1">
      {keys.split(" ").map((key, i) => (
        <kbd key={i} className="min-w-5 rounded border border-line bg-canvas px-1 text-center text-[11px] text-muted">
          {key}
        </kbd>
      ))}
    </span>
  );
}

/** ``?``: every shortcut, from the same list the keys are handled by. */
export function ShortcutHelp({ onClose }: { onClose: () => void }) {
  return (
    <Modal onClose={onClose} label="鍵盤快捷鍵" className="m-auto w-[min(32rem,calc(100vw-2rem))] rounded-xl border border-line p-0 shadow-xl">
      <div className="flex items-center justify-between border-b border-line px-5 py-3">
        <h2 className="text-base font-semibold">鍵盤快捷鍵</h2>
        <button type="button" onClick={onClose} aria-label="關閉" className="rounded p-1 text-muted hover:bg-canvas hover:text-ink">
          <Icon name="close" className="size-4" />
        </button>
      </div>
      <div className="grid max-h-[70vh] gap-4 overflow-y-auto px-5 py-4 sm:grid-cols-2">
        {SHORTCUTS.map((section) => (
          <section key={section.group}>
            <h3 className="mb-1 text-xs font-semibold text-muted">{section.group}</h3>
            <dl className="grid gap-1 text-sm">
              {section.items.map((item) => (
                <div key={item.keys} className="flex items-center justify-between gap-3">
                  <dt>{item.label}</dt>
                  <dd>
                    <Keys keys={item.keys} />
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
    </Modal>
  );
}
