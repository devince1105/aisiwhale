// A published article as readers see it (T-515): text, date, byline, the sources behind it, and
// the other languages it was published in. Server-rendered; the beacon and the reading tools
// (listen, print: D-047) are its only client parts.
import Link from "next/link";

import type { PublicArticle } from "./api";
import { listHref } from "./ArticleList";
import { Beacon } from "./Beacon";
import { CoverFigure } from "./Cover";
import { StocksNamed } from "./StocksNamed";
import { filterName, formatDate, isLang, isSection, LANG_NAMES, revisedOn, tagsOf, topicOf, words, type Lang } from "./i18n";
import { MembersOnly } from "./MembersOnly";
import { ListenButton, PrintButton, TOOL_BUTTON } from "./ReadingTools";

export function ArticleView({ article, lang }: { article: PublicArticle; lang: Lang }) {
  const w = words(lang);
  const others = Object.entries(article.langs).filter(([other]) => other !== lang && isLang(other));
  const section = isSection(article.section) ? article.section : null;
  const spoken = [article.title, ...(article.summary ? [article.summary] : []), ...article.blocks.map((b) => b.text)];
  return (
    // the column's full width beside the sidebar; narrower alone, so lines stay readable (D-146)
    <article className="max-w-3xl pt-6 pb-10 lg:max-w-none">
      <nav aria-label="breadcrumb" className="text-sm text-muted print:hidden">
        <Link href={`/news/${lang}`} className="hover:text-ink">
          {w.site}
        </Link>
        {/* a section inside a tab of several (持股觀察) has the tab first, then itself */}
        {section && tagsOf(topicOf(section)).length ? (
          <>
            <span className="mx-2">/</span>
            <Link href={listHref(lang, topicOf(section))} className="hover:text-ink">
              {filterName(lang, topicOf(section))}
            </Link>
          </>
        ) : null}
        {section ? (
          <>
            <span className="mx-2">/</span>
            <Link href={listHref(lang, section)} className="hover:text-ink">
              {w.sections[section]}
            </Link>
          </>
        ) : null}
      </nav>
      <header className="mt-6 mb-10">
        {/* D-170: the section on the left, what a reader can do with the article on the right —
            another language first (a reader who needs it looks for it), then listen, then print */}
        <div className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          {section ? <p className="text-sm font-semibold text-accent">{w.sections[section]}</p> : <span />}
          <div className="flex flex-wrap items-center gap-2 print:hidden">
            {others.map(([other, path]) => (
              <Link
                key={other}
                href={path}
                hrefLang={other}
                title={`${w.readIn}${LANG_NAMES[other as Lang]}`}
                className={TOOL_BUTTON}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                  <circle cx="12" cy="12" r="10" />
                  <path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20" />
                </svg>
                {LANG_NAMES[other as Lang]}
              </Link>
            ))}
            <ListenButton lang={lang} texts={spoken} />
            <PrintButton lang={lang} />
          </div>
        </div>
        <h1 className="font-display text-3xl leading-snug font-bold sm:text-4xl sm:leading-tight">{article.title}</h1>
        {article.summary ? <p className="mt-4 text-lg leading-relaxed text-muted">{article.summary}</p> : null}
        <p className="mt-5 text-sm text-muted">
          {/* the site's own name in the page's language, not the company's one spelling (D-043) */}
          <span>{w.site}・</span>
          {w.published} <time dateTime={article.published_at} className="text-date">{formatDate(lang, article.published_at)}</time>
          {/* revised the day it was published: that date is already there */}
          {article.revised_at && revisedOn(lang, article.published_at, article.revised_at) ? (
            <>
              {" ・ "}
              {w.revised}{" "}
              <time dateTime={article.revised_at} className="text-date">
                {revisedOn(lang, article.published_at, article.revised_at)}
              </time>
            </>
          ) : null}
        </p>
        {article.unlocked ? (
          <p data-testid="unlocked" className="mt-3">
            <span className="rounded-full border border-accent/40 px-2 py-px text-xs font-semibold text-accent">
              {w.unlock.unlocked}
            </span>
          </p>
        ) : null}
        <StocksNamed stocks={article.stocks} lang={lang} />
      </header>
      {article.cover ? <CoverFigure cover={article.cover} lang={lang} /> : null}

      {/* Chinese reads best with room between the lines, and is never set in italics */}
      <div className="space-y-6 text-[1.0625rem] leading-[1.9] sm:text-lg">
        {article.blocks.map((block, index) => {
          if (block.type === "heading") {
            return (
              <h2 key={index} className="pt-4 font-display text-2xl leading-snug font-bold">
                {block.text}
              </h2>
            );
          }
          if (block.type === "quote") {
            return (
              <blockquote key={index} className="rounded-r-lg border-l-4 border-accent/60 bg-canvas py-3 pr-4 pl-5 text-muted">
                {block.text}
              </blockquote>
            );
          }
          return <p key={index}>{block.text}</p>;
        })}
      </div>

      {article.locked ? (
        <MembersOnly
          lang={lang}
          path={article.path}
          company={article.company_slug}
          lock={article.lock ?? "members"}
          articleId={article.article_id}
          coinPrice={article.coin_price}
        />
      ) : null}

      {article.sources.length ? (
        <section className="mt-10 border-t border-line pt-6">
          <h2 className="text-base font-semibold">{w.sources}</h2>
          <ol className="mt-3 list-decimal space-y-1.5 pl-6 text-sm break-words">
            {article.sources.map((source) => (
              <li key={source.url}>
                <a href={source.url} rel="noopener nofollow" className="text-accent underline">
                  {source.title}
                </a>{" "}
                <span className="text-muted">
                  {lang === "zh-TW" ? `（${source.site}）` : `(${source.site})`}
                </span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {article.newer || article.older ? (
        <nav className="mt-10 grid gap-3 border-t border-line pt-6 sm:grid-cols-2 print:hidden">
          {article.newer ? (
            <Link href={article.newer.path} rel="prev" className="group rounded-lg border border-line p-4 hover:border-accent">
              <span className="text-xs text-muted">← {w.newerStory}</span>
              <span className="mt-1 line-clamp-2 block font-display font-semibold group-hover:text-accent">
                {article.newer.title}
              </span>
            </Link>
          ) : (
            <span className="hidden sm:block" />
          )}
          {article.older ? (
            <Link
              href={article.older.path}
              rel="next"
              className="group rounded-lg border border-line p-4 text-right hover:border-accent"
            >
              <span className="text-xs text-muted">{w.olderStory} →</span>
              <span className="mt-1 line-clamp-2 block font-display font-semibold group-hover:text-accent">
                {article.older.title}
              </span>
            </Link>
          ) : null}
        </nav>
      ) : null}
      <p className="mt-6 text-center text-sm print:hidden">
        <Link href={`/news/${lang}`} className="text-accent hover:underline">
          {w.allStories}
        </Link>
      </p>
      <Beacon articleId={article.article_id} lang={lang} />
    </article>
  );
}
