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
    assert not re.search(r'(?:href|src)="/(?![/])', html)


def test_pages_workflow_deploys_site_on_manual_tag() -> None:
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "site-*" in workflow
    assert "path: site" in workflow
    assert "actions/deploy-pages@v4" in workflow
