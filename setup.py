from setuptools import setup, find_packages

setup(
    name="moex-bot",
    version="0.5.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "pandas",
        "numpy",
        "apscheduler",
        "prometheus-client",
        "tinkoff-invest",
        "python-telegram-bot",
        "fastapi",
        "uvicorn",
        "pydantic>=1.10,<3",
        # Additional runtime dependencies (mirrored from pyproject.toml)
        "pyyaml>=6.0",
        "python-dotenv>=1.0",
        "matplotlib>=3.7",
        "seaborn>=0.12",
        "scikit-learn>=1.3",
        "plotly>=5.18",
        "requests>=2.31",
        "python-multipart>=0.0.9",
    ],
    entry_points={
        "console_scripts": [
            "moex-live=moex_bot.run_live:main",
            "moex-backtests=moex_bot.run_backtests:main",
            "moex-server=moex_bot.run_server:main",
            "moex-all=moex_bot.run_all:main",
        ],
    },
)
