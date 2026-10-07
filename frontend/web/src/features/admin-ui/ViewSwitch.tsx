// 表格 or 看板 (AD-08): one switch on the page's header, the choice on the address (?view=board).
export function ViewSwitch({ board, onBoard }: { board: boolean; onBoard: (board: boolean) => void }) {
  return (
    <div role="group" aria-label="顯示方式" className="flex rounded-md border border-line p-0.5 text-sm">
      {(
        [
          [false, "表格"],
          [true, "看板"],
        ] as const
      ).map(([value, name]) => (
        <button
          key={name}
          type="button"
          aria-pressed={board === value}
          onClick={() => onBoard(value)}
          className={`rounded px-3 py-1 ${board === value ? "bg-accent text-accent-ink" : "text-muted hover:text-ink"}`}
        >
          {name}
        </button>
      ))}
    </div>
  );
}
