"""Public entry point for the stock analysis research agent."""

from stock_analysis_runtime_patch import scanner
from stock_analysis_universe_patch import install_universe_patch
from stock_analysis_agent_views import install_agent_views


install_universe_patch(scanner)
install_agent_views(scanner)


if __name__ == "__main__":
    scanner.main()
