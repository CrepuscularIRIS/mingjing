"""Tests for the paragraph_locator helper in claim_builder (Task W1 sub-page locator).

Tests the pure helper:
    paragraph_locator(url, raw_text, snippet) -> "url#p:N" or bare url
"""

from mingjing.claim_builder import paragraph_locator


class TestParagraphLocatorBasic:
    """Basic paragraph location by index."""

    def test_snippet_in_third_paragraph(self) -> None:
        """Snippet in 3rd paragraph (0-based index 2) returns url#p:2."""
        url = "https://example.com/page"
        raw_text = "First paragraph here.\n\nSecond paragraph content.\n\nThird paragraph has the snippet we want."
        snippet = "has the snippet we want"
        result = paragraph_locator(url, raw_text, snippet)
        assert result == f"{url}#p:2"

    def test_snippet_in_first_paragraph(self) -> None:
        """Snippet in 1st paragraph (0-based index 0) returns url#p:0."""
        url = "https://example.com/page"
        raw_text = "First paragraph with the target snippet.\n\nSecond paragraph content.\n\nThird paragraph here."
        snippet = "target snippet"
        result = paragraph_locator(url, raw_text, snippet)
        assert result == f"{url}#p:0"


class TestParagraphLocatorFallback:
    """Fallback to bare url when snippet not locatable."""

    def test_snippet_not_found_returns_bare_url(self) -> None:
        """Snippet absent from raw_text falls back to bare url (no #p:)."""
        url = "https://example.com/page"
        raw_text = "First paragraph.\n\nSecond paragraph."
        snippet = "completely absent text that is not in any paragraph"
        result = paragraph_locator(url, raw_text, snippet)
        assert result == url
        assert "#p:" not in result

    def test_none_snippet_returns_bare_url(self) -> None:
        """None snippet falls back to bare url."""
        url = "https://example.com/page"
        raw_text = "Some content here.\n\nMore content."
        result = paragraph_locator(url, raw_text, None)
        assert result == url

    def test_empty_snippet_returns_bare_url(self) -> None:
        """Empty string snippet falls back to bare url."""
        url = "https://example.com/page"
        raw_text = "Some content here.\n\nMore content."
        result = paragraph_locator(url, raw_text, "")
        assert result == url

    def test_none_raw_text_returns_bare_url(self) -> None:
        """None raw_text falls back to bare url."""
        url = "https://example.com/page"
        result = paragraph_locator(url, None, "some snippet")
        assert result == url

    def test_empty_raw_text_returns_bare_url(self) -> None:
        """Empty string raw_text falls back to bare url."""
        url = "https://example.com/page"
        result = paragraph_locator(url, "", "some snippet")
        assert result == url


class TestParagraphLocatorWhitespace:
    """Whitespace-insensitive matching."""

    def test_whitespace_insensitive_match(self) -> None:
        """Snippet differing only in whitespace still locates the correct paragraph."""
        url = "https://example.com/page"
        raw_text = (
            "First paragraph.\n\n"
            "Second   paragraph\twith   extra   whitespace  inside.\n\n"
            "Third paragraph."
        )
        # Snippet with normalized whitespace (single spaces) should still match paragraph 1
        snippet = "Second paragraph with extra whitespace inside"
        result = paragraph_locator(url, raw_text, snippet)
        assert result == f"{url}#p:1"

    def test_snippet_with_newline_whitespace_diff(self) -> None:
        """Snippet extracted from a paragraph with embedded newlines matches after normalization."""
        url = "https://example.com/doc"
        raw_text = "Intro section.\n\nPricing:\nPro   tier\tcosts   $10\nper month, billed annually.\n\nConclusion."
        snippet = "Pro tier costs $10 per month"
        result = paragraph_locator(url, raw_text, snippet)
        assert result == f"{url}#p:1"


class TestParagraphLocatorEdgeCases:
    """Edge cases for url handling."""

    def test_empty_url_returns_empty_string(self) -> None:
        """Empty url returns empty string (url as-is)."""
        result = paragraph_locator("", "Some paragraph content.", "paragraph content")
        assert result == ""

    def test_single_paragraph_text(self) -> None:
        """Single-paragraph text without blank lines: snippet in that paragraph returns url#p:0."""
        url = "https://example.com/single"
        raw_text = "This is the only paragraph and it contains the target text."
        snippet = "contains the target text"
        result = paragraph_locator(url, raw_text, snippet)
        assert result == f"{url}#p:0"
