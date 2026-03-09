from setuptools import setup, find_packages

setup(
    name="noa-contracts",
    version="0.1.0",
    packages=find_packages(include=["noa_contracts", "noa_contracts.*"]),
    install_requires=["pydantic>=2.0"],
)
