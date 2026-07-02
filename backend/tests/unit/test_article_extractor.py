from types import SimpleNamespace

import pytest

from newsintel.adapters.extractors.article_html import extract_article_html


def test_json_ld_article_body_is_extracted_with_metadata() -> None:
    body = " ".join(
        [
            "The regulator said the company must preserve records and explain its data controls."
            for _ in range(8)
        ]
    )
    html = f"""
    <html lang="en">
      <head>
        <link rel="canonical" href="/stories/regulator-company-records" />
        <script type="application/ld+json">
          {{
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": "Regulator orders company to preserve records",
            "datePublished": "2026-06-26T09:30:00Z",
            "author": {{"@type": "Person", "name": "A. Reporter"}},
            "articleBody": "{body}"
          }}
        </script>
      </head>
      <body><p>Short visible teaser.</p></body>
    </html>
    """.encode()

    article = extract_article_html(html, base_url="https://example.com/news")

    assert article.title == "Regulator orders company to preserve records"
    assert article.byline == "A. Reporter"
    assert article.published_at is not None
    assert article.canonical_url == "https://example.com/stories/regulator-company-records"
    assert article.extraction_method == "json_ld_article_body"
    assert "regulator said the company" in article.text_content
    assert article.metadata["json_ld_article_detected"] is True


def test_visible_text_fallback_filters_low_value_blocks() -> None:
    html = b"""
    <html>
      <head>
        <meta property="og:title" content="Satellite startup raises funding" />
        <meta property="article:published_time" content="Fri, 26 Jun 2026 11:00:00 GMT" />
      </head>
      <body>
        <nav>Sign in Subscribe now</nav>
        <p>Advertisement</p>
        <p>The satellite imaging startup said the funding will expand its analytics platform.</p>
        <p>Executives said the company will hire engineers and open a new operations center.</p>
      </body>
    </html>
    """

    article = extract_article_html(html, base_url="https://example.com/article")

    assert article.title == "Satellite startup raises funding"
    assert article.extraction_method == "visible_text_blocks"
    assert "Advertisement" not in article.text_content
    assert "funding will expand" in article.text_content
    assert "new operations center" in article.text_content


def test_visible_text_removes_promotional_event_boilerplate() -> None:
    html = b"""
    <html>
      <head>
        <meta property="og:title" content="Streaming ad volume law takes effect" />
        <meta property="article:published_time" content="Mon, 29 Jun 2026 09:00:00 GMT" />
      </head>
      <body>
        <div class="promo-card">
          <p>
            The first StrictlyVC of 2026 hits SF on April 30.
            Tickets are going fast. Register now.
          </p>
        </div>
        <p>
          Founder Summit ticket savings of up to $190 end June 26.
          Join 1,000+ founders and VCs for a day of networking.
        </p>
        <article>
          <p>
            California's new streaming advertisement volume law will take effect
            this week after lawmakers approved consumer protection rules.
          </p>
          <p>
            The measure requires services to keep advertisements at a similar
            loudness level to the surrounding programming.
          </p>
        </article>
      </body>
    </html>
    """

    article = extract_article_html(html, base_url="https://example.com/2026/06/29/story")

    assert "StrictlyVC" not in article.text_content
    assert "Founder Summit" not in article.text_content
    assert "advertisement volume law" in article.text_content
    assert "similar loudness level" in article.text_content
    assert article.metadata["rejected_boilerplate_count"] == 1
    assert "boilerplate_removed" in article.warnings


def test_visible_text_removes_subscription_and_loading_boilerplate() -> None:
    html = b"""
    <html>
      <head>
        <meta property="og:title" content="Expired grocery items found in warehouses" />
        <meta property="article:published_time" content="Mon, 29 Jun 2026 12:30:00 +0530" />
      </head>
      <body>
        <p>Loading...</p>
        <p>You don't have any Active Subscription.</p>
        <p>Subscribed with another email? Logout and Login with that one.</p>
        <p>Account subscription benefits alongside Premium Stories and editorial newsletters.</p>
        <main>
          <p>
            Food safety officials found expired grocery items during inspections
            at warehouses used by delivery companies.
          </p>
          <p>
            The department said notices were issued and samples were collected
            for further laboratory analysis.
          </p>
        </main>
      </body>
    </html>
    """

    article = extract_article_html(html, base_url="https://example.com/news/city/story")

    assert "Loading" not in article.text_content
    assert "Active Subscription" not in article.text_content
    assert "Premium Stories" not in article.text_content
    assert "expired grocery items" in article.text_content
    assert "laboratory analysis" in article.text_content
    assert article.metadata["rejected_boilerplate_count"] == 4
    assert "possible_subscription_boilerplate" not in article.warnings


def test_attribute_skipped_container_does_not_hide_following_article_body() -> None:
    html = b"""
    <html>
      <head>
        <meta property="og:title" content="Satellite company opens operations center" />
      </head>
      <body>
        <div class="newsletter-signup">
          <p>Subscribe now to receive updates from our sponsors and partners.</p>
        </div>
        <article>
          <p>
            The satellite company opened a new operations center to support
            image analysis for disaster response teams.
          </p>
          <p>
            Executives said the site will coordinate engineering, customer
            operations, and emergency mapping work.
          </p>
        </article>
      </body>
    </html>
    """

    article = extract_article_html(html, base_url="https://example.com/news/satellite-story")

    assert "Subscribe now" not in article.text_content
    assert "operations center" in article.text_content
    assert "emergency mapping" in article.text_content


def test_publisher_policy_name_is_recorded() -> None:
    html = b"""
    <html>
      <head><meta property="og:title" content="Example" /></head>
      <body>
        <p>
          Streaming ads might be getting quieter this week after California
          approved consumer protection rules for online video platforms.
        </p>
      </body>
    </html>
    """

    article = extract_article_html(html, base_url="https://techcrunch.com/2026/06/story/")

    assert article.metadata["publisher_extraction_policy"] == "techcrunch"


def test_partial_paywall_warning_uses_raw_html_indicators() -> None:
    html = b"""
    <html>
      <head><meta property="og:title" content="Subscriber story" /></head>
      <body>
        <div class="paywall">Subscribe to continue reading this subscriber only article.</div>
        <article>
          <p>The company said it would announce more details later this week.</p>
        </article>
      </body>
    </html>
    """

    article = extract_article_html(html, base_url="https://example.com/news/subscriber-story")

    assert "possible_paywall_or_partial_content" in article.warnings
    assert article.metadata["paywall_indicator_count"] >= 1


def test_optional_trafilatura_fallback_can_replace_weak_visible_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trafilatura_text = " ".join(
        "The company described the product launch and its safety testing process."
        for _ in range(12)
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "trafilatura",
        SimpleNamespace(extract=lambda *args, **kwargs: trafilatura_text),
    )
    html = b"""
    <html>
      <head><meta property="og:title" content="Product launch" /></head>
      <body>
        <p>A short visible article body says only that more details are expected.</p>
      </body>
    </html>
    """

    article = extract_article_html(html, base_url="https://example.com/news/product-launch")

    assert article.extraction_method == "trafilatura_fallback"
    assert article.word_count > 80
    assert article.metadata["optional_trafilatura_available"] is True
