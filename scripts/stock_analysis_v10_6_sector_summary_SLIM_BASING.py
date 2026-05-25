"""Public entry point for the stock analysis scanner."""

from stock_analysis_runtime_patch import run_patched_main, scanner


if __name__ == "__main__":
    run_patched_main()
