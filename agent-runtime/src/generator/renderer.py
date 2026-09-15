import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, StrictUndefined
import textwrap
from src.agents.schemas.generator_schema import GenerationPlan
import re   

import ast
import json
import subprocess
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)

SPEC_FILENAME = "spec.json"

class RenderError(RuntimeError):
    """The plan could not be turned into valid, runnable Python."""


@dataclass
class RenderResult:
    """What the Generator reports back to the Orchestrator."""
 
    path: Path
    spec_path: Path
    lint_ran: bool = False
    lint_findings: list[str] = field(default_factory=list)
 

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
        self.env.filters["env_token"] = self._env_token
        logger.info(f"Renderer initialized (templates_dir={templates_dir})")

    @staticmethod
    def _env_token(value: str) -> str:
        """kafka -> KAFKA; node-red -> NODE_RED. Always a valid shell identifier."""
        token = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").upper()
        if not token or token[0].isdigit():
            token = f"MCP_{token}"
        return token


    @staticmethod
    def _check_syntax(rendered: str) -> None:
        """Hard gate: never write a file that is not valid Python."""
        try:
            ast.parse(rendered)
        except SyntaxError as e:
            lines = rendered.splitlines()
            lineno = e.lineno or 1
            lo, hi = max(0, lineno - 4), min(len(lines), lineno + 3)
            context = "\n".join(
                f"{'>>' if i + 1 == lineno else '  '} {i + 1:4d} | {lines[i]}"
                for i in range(lo, hi)
            )
            raise RenderError(
                f"Generated code is not valid Python.\n"
                f"  line {lineno}, col {e.offset}: {e.msg}\n\n{context}\n\n"
                f"This is almost always a tool 'body' whose indentation is inconsistent. "
                f"Bodies must start at column 0 with nested blocks at +4."
            ) from e
 
    @staticmethod
    def _lint(path: Path) -> tuple[bool, list[str]]:
        """Soft gate. Returns (ran, findings).
 
        F      = pyflakes  (undefined names, unused imports, redefinitions)
        B      = bugbear   (mutable default arguments, ...)
        ASYNC  = blocking calls inside async functions
 
        `ran` is False when ruff is unavailable, so spec.json can tell the
        Reviewer the truth instead of claiming a check that never happened.
        """
        cmd = ["ruff", "check", "--select", "F,B,ASYNC",
               "--output-format", "concise", str(path)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except FileNotFoundError:
            logger.warning("ruff not installed - lint gate skipped (pip install ruff)")
            return False, []
        except subprocess.TimeoutExpired:
            logger.warning("ruff timed out - lint gate skipped")
            return False, []
 
        findings = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip() and ": " in ln and not ln.startswith(("Found ", "[*]"))]
        if findings:
            logger.warning("ruff found %d issue(s) in %s", len(findings), path.name)
        return True, findings
 

 
    def _write_spec(
        self,
        plan: GenerationPlan,
        output_dir: Path,
        lint_ran: bool,
        lint_findings: list[str],
    ) -> Path:
        """Sidecar the Reviewer reads from the shared generated/ volume.
 
        review_code sends only a file path over A2A. Rather than change that
        message shape, the Reviewer looks for this file next to the .py it was
        handed. Without it the Reviewer cannot check completeness and will
        raise unfixable issues inside verbatim blocks.
        """
        spec = {
            "technology": plan.technology_pascal,
            "technology_lower": plan.technology_lower,
            "required_capabilities": plan.required_capabilities,
            "verbatim_functions": plan.verbatim_functions,
            "declared_tools": [
                {"name": t.name, "signature": t.params_signature, "returns": t.return_type}
                for t in plan.tools
            ],
            "lint_ran": lint_ran,
            "lint_findings": lint_findings,
            "uncertainties": plan.uncertainties,
        }
        spec_path = output_dir / SPEC_FILENAME
        spec_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        return spec_path

    def render(self, plan: GenerationPlan, output_dir: Path) -> RenderResult:
        """
        Render a GenerationPlan into a server.py file in the output directory.
 
        Raises RenderError if the result is not valid Python.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        template = self.env.get_template("server.py.j2")
        rendered = template.render(**plan.model_dump())

        self._check_syntax(rendered)
        

        filename = f"{plan.technology_lower}_server.py"
        output_path = output_dir / filename
        output_path.write_text(rendered, encoding="utf-8")

        lint_ran, lint_findings = self._lint(output_path)
        spec_path = self._write_spec(plan, output_dir, lint_ran, lint_findings)

        logger.info(
            "Wrote %s (%d chars, lint_ran=%s, %d finding(s))",
            output_path, len(rendered), lint_ran, len(lint_findings),
        )
        return RenderResult(
            path=output_path,
            spec_path=spec_path,
            lint_ran=lint_ran,
            lint_findings=lint_findings,
        )

