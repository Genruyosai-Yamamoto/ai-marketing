from website_analyzer import analyze_html


HTML = b"""
<html><head>
<title>Example Domain</title>
<meta name="description" content="A nice description.">
</head><body>
<h1>Welcome</h1>
<a href="/pricing">Pricing</a>
</body></html>
"""


def test_analyze_html_emits_meta_description():
    analysis = analyze_html(HTML)
    assert analysis["description"] == "A nice description."
    assert analysis["meta_description"] == "A nice description."


def test_analyze_html_existing_fields_unchanged():
    analysis = analyze_html(HTML)
    assert analysis["title"] == "Example Domain"
    assert analysis["headings"] == ["Welcome"]
    assert analysis["links"] == [{"text": "Pricing", "href": "/pricing"}]