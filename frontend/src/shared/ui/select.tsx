import { Check } from "lucide-react";
import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { cn } from "@/shared/lib/cn";

export type SelectOption = {
  value: string;
  label: ReactNode;
  /** Plain text used by type-ahead when `label` is not a string. */
  text?: string;
  disabled?: boolean;
};

type MenuPosition = {
  top: number;
  left: number;
  width: number;
  maxHeight: number;
};

function optionText(option: SelectOption): string {
  return option.text ?? (typeof option.label === "string" ? option.label : option.value);
}

/**
 * A designed listbox that keeps the platform behaviour of a native select (keyboard,
 * ARIA, focus) but lets the option list follow the KEMETRA tokens instead of the OS
 * widget. The menu is portalled so cards' `backdrop-filter` cannot become its
 * containing block, and it is re-scoped to the trigger's theme (the benchmark subtree
 * stays light inside the dark shell).
 */
export function SelectControl({
  id,
  value,
  options,
  onChange,
  ariaLabel,
  ariaLabelledBy,
  className,
  menuClassName,
  disabled,
  placeholder = "—",
  style,
}: {
  id?: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  ariaLabel?: string;
  ariaLabelledBy?: string;
  className?: string;
  menuClassName?: string;
  disabled?: boolean;
  placeholder?: string;
  style?: CSSProperties;
}) {
  const autoId = useId();
  const controlId = id ?? autoId;
  const listId = `${controlId}-listbox`;
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [position, setPosition] = useState<MenuPosition | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const typed = useRef({ text: "", at: 0 });

  const selectedIndex = options.findIndex((option) => option.value === value);
  const selected = selectedIndex >= 0 ? options[selectedIndex] : undefined;

  const firstEnabled = (from: number, step: 1 | -1) => {
    if (!options.length) return 0;
    for (let offset = 0; offset < options.length; offset += 1) {
      const index = (from + offset * step + options.length * options.length) % options.length;
      if (!options[index]?.disabled) return index;
    }
    return from;
  };

  const openMenu = () => {
    if (disabled) return;
    setActive(selectedIndex >= 0 ? selectedIndex : firstEnabled(0, 1));
    setOpen(true);
  };

  const closeMenu = (focusTrigger = false) => {
    setOpen(false);
    setPosition(null);
    if (focusTrigger) triggerRef.current?.focus();
  };

  const choose = (index: number) => {
    const option = options[index];
    if (!option || option.disabled) return;
    onChange(option.value);
    closeMenu(true);
  };

  // Place the menu against the trigger, flipping above when there is no room below.
  useLayoutEffect(() => {
    if (!open) return;
    const update = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const gap = 4;
      const margin = 8;
      const menuHeight = menuRef.current?.scrollHeight ?? 0;
      const below = window.innerHeight - rect.bottom - gap - margin;
      const above = rect.top - gap - margin;
      const flip = menuHeight > below && above > below;
      const maxHeight = Math.max(96, Math.min(menuHeight || 280, flip ? above : below));
      const width = Math.max(rect.width, 180);
      setPosition({
        top: flip ? Math.max(margin, rect.top - maxHeight - gap) : rect.bottom + gap,
        left: Math.max(margin, Math.min(rect.left, window.innerWidth - width - margin)),
        width,
        maxHeight,
      });
      const activeOption = menuRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`);
      activeOption?.scrollIntoView({ block: "nearest" });
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open, active]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      closeMenu();
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  const typeAhead = (key: string) => {
    const now = Date.now();
    const prefix = (now - typed.current.at > 700 ? "" : typed.current.text) + key.toLowerCase();
    typed.current = { text: prefix, at: now };
    const match = options.findIndex(
      (option) => !option.disabled && optionText(option).toLowerCase().startsWith(prefix),
    );
    if (match >= 0) setActive(match);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
        event.preventDefault();
        openMenu();
      }
      return;
    }
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActive((index) => firstEnabled(index + 1, 1));
        break;
      case "ArrowUp":
        event.preventDefault();
        setActive((index) => firstEnabled(index - 1, -1));
        break;
      case "Home":
        event.preventDefault();
        setActive(firstEnabled(0, 1));
        break;
      case "End":
        event.preventDefault();
        setActive(firstEnabled(options.length - 1, -1));
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        choose(active);
        break;
      case "Escape":
        event.preventDefault();
        closeMenu(true);
        break;
      case "Tab":
        closeMenu();
        break;
      default:
        if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
          typeAhead(event.key);
        }
    }
  };

  const themeHost = triggerRef.current?.closest<HTMLElement>("[data-theme]");
  const tema = themeHost?.dataset.theme;
  const astryxTheme = themeHost?.dataset.astryxTheme;

  return (
    <div className="relative min-w-0" style={style}>
      <button
        ref={triggerRef}
        id={controlId}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={open ? `${listId}-${active}` : undefined}
        aria-label={ariaLabel}
        aria-labelledby={ariaLabelledBy}
        disabled={disabled}
        onClick={() => (open ? closeMenu() : openMenu())}
        onKeyDown={onKeyDown}
        className={cn(
          "select-control flex w-full items-center text-start",
          open && "is-open",
          className,
        )}
      >
        <span className={cn("min-w-0 truncate", !selected && "text-muted")}>
          {selected?.label ?? placeholder}
        </span>
      </button>
      {open
        ? createPortal(
            <div
              ref={menuRef}
              id={listId}
              role="listbox"
              aria-labelledby={ariaLabelledBy ?? controlId}
              tabIndex={-1}
              data-theme={tema}
              data-astryx-theme={astryxTheme}
              className={cn("select-menu", menuClassName)}
              style={{
                top: position?.top ?? 0,
                left: position?.left ?? 0,
                width: position?.width ?? triggerRef.current?.offsetWidth,
                maxHeight: position?.maxHeight ?? 320,
                visibility: position ? "visible" : "hidden",
              }}
            >
              {options.map((option, index) => {
                const isSelected = option.value === value;
                return (
                  <div
                    key={option.value}
                    id={`${listId}-${index}`}
                    role="option"
                    aria-selected={isSelected}
                    aria-disabled={option.disabled || undefined}
                    data-index={index}
                    data-active={index === active || undefined}
                    className={cn(
                      "select-option",
                      index === active && "is-active",
                      option.disabled && "is-disabled",
                    )}
                    onPointerMove={() => {
                      if (!option.disabled) setActive(index);
                    }}
                    onClick={() => choose(index)}
                  >
                    <span className="select-option-label">{option.label}</span>
                    {isSelected ? (
                      <Check aria-hidden="true" className="size-3.5 shrink-0 text-accent" />
                    ) : null}
                  </div>
                );
              })}
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}

/** Labelled listbox, the designed counterpart of the native `<select>` + `<label>` pair. */
export function Select({
  label,
  help,
  className,
  ...props
}: Omit<Parameters<typeof SelectControl>[0], "ariaLabel"> & {
  label: string;
  help?: string;
  className?: string;
}) {
  const id = props.id ?? useId();
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <span id={`${id}-label`} className="text-xs font-medium text-text-2">
        {label}
      </span>
      <SelectControl {...props} id={id} ariaLabelledBy={`${id}-label`} />
      {help ? <p className="text-xs text-muted">{help}</p> : null}
    </div>
  );
}
