from setuptools import setup, find_packages

setup(
    name="name_change_bot",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "telethon",
        "python-dotenv",
        "aiohttp",
    ],
    python_requires=">=3.7",
) 