/**
 * Panel — KEMETRA glass panel built on @astryxdesign/core primitives.
 *
 * Wraps Card + Layout + LayoutHeader/Content/Footer so no feature file
 * ever imports Astryx directly — keeping migration reversible.
 *
 * Scope: Dashboard, Overview, Assistant tabs only.
 *       Do NOT use in live-map or events tab.
 */
import { Card } from "@astryxdesign/core/Card";
import {
  Layout,
  LayoutContent,
  LayoutFooter,
  LayoutHeader,
} from "@astryxdesign/core/Layout";
import { Heading } from "@astryxdesign/core/Heading";
import type { ReactNode } from "react";

export interface PanelProps {
  /** Optional heading rendered in the panel header with a divider below. */
  title?: string;
  /** Heading semantic level (default: 2). */
  headingLevel?: 1 | 2 | 3 | 4 | 5 | 6;
  /** Optional footer content rendered with a divider above. */
  footer?: ReactNode;
  /** Main body content. */
  children: ReactNode;
  /** Pixel width or CSS value (e.g. "100%"). Defaults to full width. */
  width?: number | string;
  /** Extra class names on the wrapping Card. */
  className?: string;
  /** Accessible label for the section. */
  "aria-label"?: string;
  /** aria-labelledby id. */
  "aria-labelledby"?: string;
}

/**
 * Glass panel with optional header, scrollable body, and footer.
 *
 * @example
 * ```tsx
 * <Panel title="KPI Overview" footer={<HStack hAlign="end"><KButton label="Export" /></HStack>}>
 *   <KpiGrid metrics={kpis} />
 * </Panel>
 * ```
 */
export function Panel({
  title,
  headingLevel = 2,
  footer,
  children,
  width,
  className,
  "aria-label": ariaLabel,
  "aria-labelledby": ariaLabelledby,
}: PanelProps) {
  return (
    <div
      data-astryx-theme="astryx"
      className={className}
      style={{ width }}
      aria-label={ariaLabel}
      aria-labelledby={ariaLabelledby}
    >
      <Card>
        <Layout
          header={
            title ? (
              <LayoutHeader hasDivider>
                <Heading level={headingLevel}>{title}</Heading>
              </LayoutHeader>
            ) : undefined
          }
          content={<LayoutContent>{children}</LayoutContent>}
          footer={
            footer ? (
              <LayoutFooter hasDivider>{footer}</LayoutFooter>
            ) : undefined
          }
        />
      </Card>
    </div>
  );
}
