import { Code2, Search } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { normalize } from "@/app/command/filter";
import { useGuide } from "@/shared/api/queries";
import { SourceNote } from "@/shared/components/evidence";
import { Details, PageHero } from "@/shared/components/page";
import { QueriesState } from "@/shared/components/QueriesState";
import { cn } from "@/shared/lib/cn";
import { usePageTitle } from "@/shared/lib/use-page-title";
import type { Guide } from "@/shared/schemas/combined";

/**
 * The document's links point to code files of the repository: in the dashboard they are
 * shown as code references (the excerpts themselves are under each part).
 */
function reference(href: string | undefined, children: ReactNode) {
  if (href && /^https?:/.test(href))
    return (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="text-text underline underline-offset-4"
      >
        {children}
      </a>
    );
  return (
    <code className="rounded bg-surface-3 px-1.5 py-0.5 font-mono text-[0.85em] text-text">
      {children}
    </code>
  );
}

const MD: Components = {
  h3: ({ children }) => <h4 className="mt-5 mb-2 text-base font-semibold text-text">{children}</h4>,
  p: ({ children }) => <p className="my-2.5 text-[15px] leading-relaxed text-text-2">{children}</p>,
  ul: ({ children }) => (
    <ul className="my-2.5 list-disc space-y-1.5 ps-6 text-[15px] text-text-2">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="my-2.5 list-decimal space-y-1.5 ps-6 text-[15px] text-text-2">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-text">{children}</strong>,
  a: ({ href, children }) => reference(href, children),
  blockquote: ({ children }) => (
    <blockquote className="my-3 rounded-lg border-s-4 border-[var(--ctl-candidate)] bg-surface-2 px-4 py-1">
      {children}
    </blockquote>
  ),
  code: ({ className, children }) =>
    className ? (
      <code className="font-mono text-[13px]">{children}</code>
    ) : (
      <code className="rounded bg-surface-3 px-1.5 py-0.5 font-mono text-[0.85em] text-text">
        {children}
      </code>
    ),
  pre: ({ children }) => (
    <pre className="my-3 overflow-x-auto rounded-lg border border-border bg-surface-2 p-3 text-[13px] leading-relaxed text-text [&_code]:bg-transparent [&_code]:p-0">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div
      tabIndex={0}
      role="region"
      aria-label="tableau"
      className="my-3 overflow-x-auto rounded-lg border border-border"
    >
      <table className="w-full min-w-[520px] text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-surface-2 text-xs text-text-2">{children}</thead>,
  th: ({ children }) => <th className="px-3 py-2 text-start font-medium">{children}</th>,
  td: ({ children }) => (
    <td className="border-t border-border px-3 py-2 align-top text-text-2">{children}</td>
  ),
  hr: () => <hr className="my-6 border-border" />,
};

export default function GuidePage() {
  const { t } = useTranslation();
  usePageTitle(t("nav.guide"));
  const queries = { guide: useGuide() };
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-8">
      <QueriesState queries={queries} height={480}>
        {({ guide }) => <Content guide={guide} />}
      </QueriesState>
    </div>
  );
}

function Content({ guide }: { guide: Guide }) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const shown = useMemo(() => {
    const words = normalize(query).split(/\s+/).filter(Boolean);
    if (!words.length) return guide.sections;
    return guide.sections.filter((s) => {
      const text = normalize(`${s.number} ${s.title} ${s.markdown}`);
      return words.every((w) => text.includes(w));
    });
  }, [guide.sections, query]);
  return (
    <>
      <PageHero
        eyebrow={t("guide.eyebrow")}
        title={t("guide.title")}
        answer={t("guide.answer", { parts: guide.sections.length, excerpts: guide.code.length })}
      >
        <div className="max-w-3xl [&_p]:text-sm">
          <Markdown remarkPlugins={[remarkGfm]} components={MD}>
            {guide.intro}
          </Markdown>
        </div>
      </PageHero>

      <div className="grid gap-8 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-4 lg:self-start">
          <label className="mb-3 flex items-center gap-2 rounded-lg border border-border bg-surface px-3">
            <Search aria-hidden="true" className="size-4 text-muted" />
            <span className="sr-only">{t("guide.search")}</span>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("guide.search")}
              className="h-10 min-w-0 flex-1 bg-transparent text-sm text-text outline-none placeholder:text-muted"
            />
          </label>
          <nav
            aria-label={t("guide.toc")}
            className="max-h-[70vh] overflow-y-auto rounded-xl border border-border bg-surface p-2"
          >
            <ol className="flex flex-col gap-0.5 text-sm">
              {guide.sections.map((s) => {
                const visible = shown.includes(s);
                return (
                  <li key={s.id}>
                    <a
                      href={`#${s.id}`}
                      className={cn(
                        "flex gap-2 rounded-md px-2.5 py-1.5 hover:bg-surface-2",
                        visible ? "text-text-2 hover:text-text" : "text-muted opacity-50",
                      )}
                    >
                      <span className="tabular w-9 shrink-0 font-mono text-xs text-muted">
                        {s.number}
                      </span>
                      <span className="leading-snug">{s.title}</span>
                    </a>
                  </li>
                );
              })}
            </ol>
          </nav>
        </aside>

        <div className="flex min-w-0 flex-col gap-6">
          {shown.length ? null : <p className="text-sm text-muted">{t("guide.empty")}</p>}
          {shown.map((s) => (
            <Part key={s.id} section={s} code={guide.code.filter((c) => c.part === s.number)} />
          ))}
          <SourceNote source={guide.source} extra={`commit ${guide.commit}`} />
        </div>
      </div>
    </>
  );
}

function Part({ section, code }: { section: Guide["sections"][number]; code: Guide["code"] }) {
  const { t } = useTranslation();
  return (
    <section
      id={section.id}
      aria-labelledby={`${section.id}-title`}
      className="scroll-mt-4 rounded-2xl border border-border bg-surface p-5 md:p-7"
    >
      <h2
        id={`${section.id}-title`}
        className="flex items-baseline gap-3 text-xl font-semibold tracking-tight text-text"
      >
        <span className="font-mono text-base text-muted">{section.number}</span>
        {section.title}
      </h2>
      <Markdown remarkPlugins={[remarkGfm]} components={MD}>
        {section.markdown}
      </Markdown>
      {code.length ? (
        <div className="mt-4">
          <Details title={t("guide.code", { n: code.length })} hint={t("guide.codeHint")}>
            <div className="flex flex-col gap-4">
              {code.map((c) => (
                <Excerpt key={`${c.file}:${c.start}`} excerpt={c} />
              ))}
            </div>
          </Details>
        </div>
      ) : null}
    </section>
  );
}

function Excerpt({ excerpt }: { excerpt: Guide["code"][number] }) {
  const lines = excerpt.code.split("\n");
  return (
    <figure className="overflow-hidden rounded-lg border border-border">
      <figcaption className="flex flex-wrap items-center gap-2 border-b border-border bg-surface-2 px-3 py-2 text-xs">
        <Code2 aria-hidden="true" className="size-3.5 text-muted" />
        <span className="font-medium text-text">{excerpt.title}</span>
        <span className="font-mono text-muted">
          {excerpt.file}:{excerpt.start}–{excerpt.end}
          {excerpt.name ? ` · ${excerpt.name}` : ""}
        </span>
      </figcaption>
      <pre
        tabIndex={0}
        role="region"
        aria-label={`${excerpt.file}:${excerpt.start}`}
        className="max-h-[420px] overflow-auto bg-surface py-2 text-[12.5px] leading-relaxed"
      >
        <code className="font-mono">
          {lines.map((line, i) => (
            <span key={i} className="flex">
              <span
                aria-hidden="true"
                className="tabular w-12 shrink-0 pe-3 text-end text-muted select-none"
              >
                {excerpt.start + i}
              </span>
              <span className="pe-4 whitespace-pre text-text">{line || " "}</span>
            </span>
          ))}
        </code>
      </pre>
    </figure>
  );
}
