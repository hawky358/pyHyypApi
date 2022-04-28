import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name='pyhyypapi',
    version="0.0.0.1",
    license='Apache Software License 2.0',
    author='Renier Moorcroft',
    author_email='renierm26@users.github.com',
    description='IDS Hyyp/ADT Secure Home API',
    long_description="API for accessing IDS Hyyp. This is used by ADT Home Connect and possibly others. Please view readme on github",
    url='https://github.com/RenierM26/pyadtsecurehome/',
    packages=setuptools.find_packages(),
    setup_requires=[
        'requests',
        'setuptools'
    ],
    install_requires=[
        'requests',
        'pandas',
        'pycryptodome'
    ],
    entry_points={
    'console_scripts': ['pyhyypapi = pyhyypapi.__main__:main']
    },
    python_requires = '>=3.6'
)
