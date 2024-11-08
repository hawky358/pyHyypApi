import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name='pyhyypapihawkmod',
    version="1.5.1",
    license='Apache Software License 2.0',
    author='hawky358',
    author_email='hawky358@users.github.com',
    description='IDS Hyyp/ADT Secure Home API',
    long_description="API for accessing IDS Hyyp. This is used by ADT Home Connect and possibly others.",
    url='https://github.com/hawky358/pyHyypApi',
    packages=setuptools.find_packages(),
    setup_requires=[
        'requests',
        'setuptools'
    ],
    install_requires=[
        'requests',
        'pandas',
        'oscrypto',
        'protobuf',
        'http-ece',
        'firebase_messaging==0.4.4',
        'appdirs'
    ],
    python_requires = '>=3.6'
)
