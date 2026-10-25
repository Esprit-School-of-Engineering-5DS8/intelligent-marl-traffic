/**
 * KButton — KEMETRA button built on @astryxdesign/core/Button.
 *
 * Thin wrapper so feature files don't import Astryx directly.
 * Scope: Dashboard, Overview, Assistant tabs only.
 */
import { Button as AstryxButton } from "@astryxdesign/core/Button";
import type { ReactNode } from "react";

export interface KButtonProps {
  /** Button label text (also serves as accessible name). */
  label: string;
  /** Visual variant. Defaults to "secondary". */
  variant?: "primary" | "secondary" | "ghost";
  /** Size. Defaults to "md". */
  size?: "sm" | "md" | "lg";
  /** Click handler. */
  onClick?: React.MouseEventHandler<HTMLButtonElement>;
  /** Disabled state. */
  isDisabled?: boolean;
  /** Icon element rendered before the label. */
  icon?: ReactNode;
  /** Content rendered after the label (badge, icon, chevron, etc.). */
  endContent?: ReactNode;
  /** Tooltip text shown on hover. */
  tooltip?: string;
  /** HTML button type. */
  type?: "button" | "submit" | "reset";
  /** Width in pixels or CSS string (e.g. "100%"). */
  width?: number | string;
}

export function KButton({
  label,
  variant = "secondary",
  size = "md",
  onClick,
  isDisabled,
  icon,
  endContent,
  tooltip,
  type = "button",
  width,
}: KButtonProps) {
  return (
    <div data-astryx-theme="astryx">
      <AstryxButton
        label={label}
        variant={variant}
        size={size}
        onClick={onClick}
        isDisabled={isDisabled}
        icon={icon}
        endContent={endContent}
        tooltip={tooltip}
        type={type}
        width={width}
      />
    </div>
  );
}
