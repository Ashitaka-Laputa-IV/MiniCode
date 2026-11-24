import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def test_project_site_files_exist() -> None:
    assert (SITE / "index.html").is_file()
    assert (SITE / "styles.css").is_file()
    assert (SITE / "app.js").is_file()
    assert (SITE / "assets" / "favicon.svg").is_file()


def test_project_site_is_bilingual() -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert 'data-lang="zh"' in html
    assert 'data-lang-button="en"' in html
    assert 'class="lang-zh"' in html
    assert 'class="lang-en"' in html


def test_project_site_uses_relative_assets() -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert 'href="./styles.css"' in html
    assert 'src="./app.js"' in html
    assert 'href="./assets/favicon.svg"' in html
    assert "DEEPSEEK_API_KEY" in html
    assert "OPENCODE_GO_API_KEY" in html
    assert not re.search(r'(?:href|src)="/(?![/])', html)


def test_pages_workflow_deploys_pinned_actions_on_manual_tag() -> None:
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "site-*" in workflow
    assert "path: site" in workflow
    for action in (
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "actions/configure-pages@45bfe0192ca1faeb007ade9deae92b16b8254a0d",
        "actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9",
        "actions/deploy-pages@368f82528645a54fb793d4d04e342629a3f51346",
    ):
        assert action in workflow
