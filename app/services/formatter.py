from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import urlsplit

from app.models import Article

IST = timezone(timedelta(hours=5, minutes=30), "IST")
FOOTER = "AI summaries based on source feed titles and descriptions."


@dataclass(frozen=True)
class Email:
    subject: str
    html: str
    text: str


def _format_date(now: datetime) -> str:
    local = now.astimezone(IST)
    return f"{local:%A}, {local.day} {local:%B %Y}"


def _check_link(link: str) -> None:
    parts = urlsplit(link)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("Article links must be valid HTTP or HTTPS URLs.")


def _render_article(index: int, article: Article) -> str:
    _check_link(article.link)
    return f"""<h2 style="font-size:18px;margin:24px 0 8px;padding-top:16px;border-top:1px solid #e5e7eb;">
    {index + 1}. <a href="{escape(article.link)}" style="color:#2563eb;">{escape(article.title)}</a>
  </h2>
  <p style="font-size:12px;color:#6b7280;margin:0 0 8px;">Source: {escape(article.source)}</p>
  <p style="font-size:15px;line-height:1.6;margin:0;">{escape(article.summary)}</p>"""


def format_email(articles: list[Article], now: datetime | None = None) -> Email:
    now = now or datetime.now(timezone.utc)
    date = _format_date(now)
    count = f"{len(articles)} {'story' if len(articles) == 1 else 'stories'} selected."

    if articles:
        content = "\n".join(_render_article(index, article) for index, article in enumerate(articles))
    else:
        content = "<p>No new stories today.</p>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Briefly</title>
</head>
<body style="margin:0;padding:24px 12px;background-color:#f3f4f6;font-family:Arial,sans-serif;color:#111827;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;background-color:#ffffff;">
        <tr><td style="padding:24px;">
          <h1 style="font-size:26px;margin:0 0 8px;">Briefly</h1>
          <p style="color:#6b7280;font-size:14px;margin:0 0 16px;">{date}</p>
          <p>{count}</p>
          {content}
          <p style="font-size:12px;color:#6b7280;margin-top:32px;">{FOOTER}</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    lines = ["BRIEFLY", date, count, ""]
    if not articles:
        lines += ["No new stories today.", ""]
    for index, article in enumerate(articles, start=1):
        lines += [
            f"{index}. {article.title}",
            f"Source: {article.source}",
            article.summary,
            f"Read: {article.link}",
            "",
        ]
    lines.append(FOOTER)

    return Email(subject=f"Briefly — {date}", html=html, text="\n".join(lines))