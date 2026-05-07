from setuptools import find_packages, setup

setup(
    name="ppt-generator",
    version="0.1.0",
    description="PPT-Genius: LLM + RAG prototype for outline and content enrichment",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.9",
    install_requires=[
        "openai>=1.30.0",
        "python-pptx>=0.6.21",
        "rank-bm25>=0.2.2",
        "fastapi>=0.110.0",
        "uvicorn[standard]>=0.27.0",
        "python-multipart>=0.0.9",
        "pypdf>=4.0.0",
        "python-docx>=1.1.0",
        "python-dotenv>=1.0.0",
    ],
    extras_require={"dev": ["pytest>=7.0"]},
)
