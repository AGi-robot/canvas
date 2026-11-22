from setuptools import find_namespace_packages, setup


setup(
    name="grace-canvas",
    version="0.2.0",
    description="Grace's vector drawing engine: action language, SVG renderer, stroke dynamics and palette harmonization",
    python_requires=">=3.10",
    package_dir={"": "src"},
    packages=find_namespace_packages(where="src"),
    extras_require={"test": ["pytest", "jsonschema"]},
    entry_points={"console_scripts": ["canvas = canvas.cli:main"]},
)
