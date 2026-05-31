from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent
_CONTEXT_DIR = _PROMPTS_DIR.parent / "context"


def render_prompt(name: str, **context: str) -> str:
    template_path = _PROMPTS_DIR / f"{name}.md"
    if not template_path.is_file():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    template = template_path.read_text(encoding="utf-8")
    return template.format(**context)


def load_cluster_context() -> str:
    return (_CONTEXT_DIR / "cluster.md").read_text(encoding="utf-8")
