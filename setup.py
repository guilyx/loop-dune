from setuptools import setup, find_packages

setup(
    name="loop-dune",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "python-dotenv>=1.0.1",
        "pandas>=2.2.1",
        "eth-typing>=4.0.0",
        "tqdm>=4.66.2",
        "colorama>=0.4.6",
        "requests>=2.31.0",
        "streamlit>=1.32.0",
        "plotly>=5.19.0",
        "schedule>=1.2.1",
        "web3>=6.10.0",
        "setuptools>=78.1.0",
    ],
    python_requires=">=3.9,!=3.9.7",
)
