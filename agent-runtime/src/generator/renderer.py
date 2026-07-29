import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, StrictUndefined
import textwrap
from src.agents.schemas.generator_schema import GenerationPlan

logger = logging.getLogger(__name__)


class Renderer:
    """Renders a GenerationPlan into a Python file using Jinja templates."""

    def __init__(self, templates_dir: Path | None = None):
        # Default: templates/ folder next to this file
        if templates_dir is None:
            templates_dir = Path(__file__).parent / "templates"

        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            undefined=StrictUndefined,
        )
        self.env.filters["dedent"] = textwrap.dedent
        logger.info(f"Renderer initialized (templates_dir={templates_dir})")

    def render(self, plan: GenerationPlan, output_dir: Path) -> Path:
        """
        Render a GenerationPlan into a server.py file in the output directory.

        Returns the path to the written file.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        template = self.env.get_template("server.py.j2")
        rendered = template.render(**plan.model_dump())

        filename = f"{plan.technology_lower}_server.py"
        output_path = output_dir / filename
        output_path.write_text(rendered, encoding="utf-8")

        logger.info(f"Wrote {output_path} ({len(rendered)} chars)")
        return output_path