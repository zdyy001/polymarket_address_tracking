"""
统一启动脚本
依次运行: polymarket_fetcher -> binance_fetcher -> analyze_strategy
"""
import subprocess
import sys
from pathlib import Path


def run_script(script_name: str) -> bool:
    """运行脚本并返回是否成功"""
    script_path = Path(__file__).parent / script_name

    print(f"\n{'='*60}")
    print(f"运行: {script_name}")
    print('='*60)

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=Path(__file__).parent
    )

    return result.returncode == 0


def main():
    scripts = [
        "polymarket_fetcher.py",
        "binance_fetcher.py",
        "analyze_strategy.py",
    ]

    for script in scripts:
        if not run_script(script):
            print(f"\n错误: {script} 执行失败")
            sys.exit(1)

    print(f"\n{'='*60}")
    print("全部完成!")
    print('='*60)


if __name__ == "__main__":
    main()
