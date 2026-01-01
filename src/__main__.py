import sys
from pathlib import Path

import click

from src.config import Settings, default_output_dir
from src.pipeline import PPTPipeline


@click.command()
@click.option("--input", "input_file", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--output",
    "output_dir",
    required=False,
    type=click.Path(dir_okay=True, file_okay=False, path_type=Path),
    help="输出目录（默认：ppt_outputs/<PPT名>）",
)
@click.option("--force", is_flag=True, default=False, help="强制重新运行，忽略已有 manifest")
@click.option("-v", "--verbose", is_flag=True, default=False, help="打印进度")
@click.option(
    "--config",
    "config_path",
    required=False,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=Path("config/settings.yaml"),
    show_default=True,
    help="YAML 配置文件路径",
)
@click.option("--refine", is_flag=True, default=False, help="修复模式：仅重跑低置信度页面")
@click.option("--threshold", type=float, default=0.6, help="修复模式的置信度阈值 (默认 0.6)")
def main(input_file: Path, output_dir: Path | None, force: bool, verbose: bool, config_path: Path, refine: bool, threshold: float) -> None:
    settings = Settings.from_yaml(config_path)
    target_dir = output_dir or default_output_dir(input_file)
    pipeline = PPTPipeline(settings=settings, verbose=verbose)
    
    if refine:
        manifest = pipeline.refine(pptx_path=input_file, output_dir=target_dir, threshold=threshold)
    else:
        manifest = pipeline.run(pptx_path=input_file, output_dir=target_dir, force_rerun=force)
        
    click.echo(f"完成，manifest: {target_dir / 'manifest.json'}")
    if manifest.get("errors"):
        click.echo(f"存在错误: {manifest['errors']}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
